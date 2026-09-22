package com.gpcombine.assistant.net

import com.gpcombine.assistant.ble.BleTransport
import com.gpcombine.assistant.proto.DeviceInfo
import com.gpcombine.assistant.proto.EspConfig
import com.gpcombine.assistant.proto.Frame
import com.gpcombine.assistant.proto.InfoCodec
import com.gpcombine.assistant.proto.LogCodec
import com.gpcombine.assistant.proto.LogEvent
import com.gpcombine.assistant.proto.PairInfo
import com.gpcombine.assistant.proto.Proto
import com.gpcombine.assistant.proto.BtSet
import com.gpcombine.assistant.proto.LedConfig
import com.gpcombine.assistant.proto.PadConfig
import com.gpcombine.assistant.proto.Profiles
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withTimeout

/** 设备回了错误帧（0x7F）。code 见 Proto.ERR_*。 */
class DeviceException(val code: Int, override val message: String) : Exception(message)

/**
 * 会话层：把"发一帧、等同一 seq 的回包"封装起来。
 *
 * 串行发送（Mutex）而不是并发：设备侧处理在主循环里，一次只推进一帧，
 * 并发发请求只会堆在它的接收队列里，回包顺序还可能和请求顺序不一致。
 *
 * pending 只在 collector 和 request 里访问，两者都跑在传入的 scope 上，
 * 所以用普通 MutableMap 就够（不要换成多线程 dispatcher）。
 */
class DeviceClient(
    private val transport: BleTransport,
    scope: CoroutineScope,
    private val timeoutMs: Long = 3000,
    private val clock: () -> Long = { System.currentTimeMillis() },
) {
    private val pending = mutableMapOf<Int, CompletableDeferred<Frame>>()
    private val lock = Mutex()
    private var nextSeq = 0

    // 设备主动推的日志。用 extraBufferCapacity 而不是无缓冲：诊断页没打开时
    // 也不能把设备那边等回包的主循环堵住（tryEmit 满了就丢，日志丢得起）。
    private val _logs = MutableSharedFlow<LogEvent>(extraBufferCapacity = 256)
    val logs: SharedFlow<LogEvent> = _logs.asSharedFlow()

    // 帧监视器：收发各记一条（含"没人认领的回包"——那种以前是静默丢掉的）
    private val _frames = MutableSharedFlow<FrameRecord>(extraBufferCapacity = 256)
    val frames: SharedFlow<FrameRecord> = _frames.asSharedFlow()

    private val collector: Job = scope.launch {
        transport.inbound.collect { onFrame(it) }
    }

    fun close() {
        collector.cancel()
        pending.values.forEach { it.cancel() }
        pending.clear()
    }

    private fun onFrame(f: Frame) {
        // 0x80 以上是设备主动推：它们不带 seq，永远等不到 pending，别当"没人要的回包"扔了
        if (Proto.isDevicePush(f.cmd)) {
            _frames.tryEmit(FrameRecord(Dir.RX, clock(), f.cmd, f.seq, f.payload, "设备推送"))
            if (f.cmd == Proto.CMD_LOG_EVT) LogCodec.parseEvent(f.payload)?.let { _logs.tryEmit(it) }
            return
        }

        val d = pending[f.seq]
        if (d == null) {
            // 迟到/重放的回包：以前是直接吞掉，现在至少留痕，不然排查时"少了那一帧"无处可查
            _frames.tryEmit(FrameRecord(Dir.RX, clock(), f.cmd, f.seq, f.payload, "无请求匹配"))
            return
        }
        _frames.tryEmit(FrameRecord(Dir.RX, clock(), f.cmd, f.seq, f.payload))
        if (f.cmd == Proto.CMD_ERR) {
            val code = if (f.payload.isNotEmpty()) f.payload[0].toInt() and 0xFF else -1
            val text = if (f.payload.size > 1) String(f.payload, 1, f.payload.size - 1) else ""
            d.completeExceptionally(DeviceException(code, text))
        } else {
            d.complete(f)
        }
    }

    private suspend fun request(cmd: Int, payload: ByteArray = Proto.EMPTY): Frame = lock.withLock {
        val seq = nextSeq and 0xFFFF
        nextSeq++
        val d = CompletableDeferred<Frame>()
        pending[seq] = d
        try {
            _frames.tryEmit(FrameRecord(Dir.TX, clock(), cmd, seq, payload))
            transport.send(Proto.build(cmd, seq, payload))
            withTimeout(timeoutMs) { d.await() }
        } finally {
            pending.remove(seq)
        }
    }

    suspend fun ping(): Boolean = request(Proto.CMD_PING).cmd == Proto.CMD_PING

    /**
     * 订阅设备日志（CMD_LOG_SUB）。mode 见 [LogCodec]：0 关 / 1 开 / 2 开且回放最近几行。
     * 设备侧断开连接会自动退订，不用 App 操心。
     */
    suspend fun logSubscribe(mode: Int, replay: Int = LogCodec.DEFAULT_REPLAY): Boolean {
        val f = request(Proto.CMD_LOG_SUB, LogCodec.subPayload(mode, replay))
        return f.payload.isNotEmpty() && f.payload[0].toInt() == 1
    }

    suspend fun auth(code: String): Boolean {
        val f = request(Proto.CMD_AUTH, code.toByteArray(Charsets.US_ASCII))
        return f.payload.isNotEmpty() && f.payload[0].toInt() == 1
    }

    /** INFO 回包的原始载荷 —— 体检要报"这一帧多少字节、要分几片"，所以不能只留解析结果。 */
    suspend fun infoRaw(): ByteArray = request(Proto.CMD_INFO).payload

    suspend fun info(): DeviceInfo = InfoCodec.parseInfo(String(infoRaw(), Charsets.US_ASCII))

    suspend fun pairInfo(): PairInfo =
        InfoCodec.parsePairInfo(String(request(Proto.CMD_PAIR_INFO).payload, Charsets.US_ASCII))

    // ---- 设置镜像（17 字节）----

    /** 读设备当前的设置镜像。长度/版本对不上就当没读到（返回 null），别把垃圾值摊给用户。 */
    suspend fun cfgGet(): EspConfig? = EspConfig.fromBytes(request(Proto.CMD_CFG_GET).payload)

    /**
     * 应用但**不**落盘。拖滑条、连点开关走这条：设备屏幕立刻变，flash 一点没动。
     * "保存到设备"才用 [cfgSet]。
     */
    suspend fun cfgApply(cfg: EspConfig): Boolean = ack(Proto.CMD_CFG_APPLY, cfg.toBytes())

    /** 应用 + 落盘（等价于设备菜单的"保存设置"，断电重启仍然保持）。 */
    suspend fun cfgSet(cfg: EspConfig): Boolean = ack(Proto.CMD_CFG_SET, cfg.toBytes())

    suspend fun cfgReset(): Boolean = ack(Proto.CMD_CFG_RESET, Proto.EMPTY)

    // ---- 手柄 / 灯光（Pico 侧的设置，改完 Pico 自己落盘）----

    suspend fun padGet(): PadConfig? = PadConfig.fromBytes(request(Proto.CMD_GP_GET).payload)

    /**
     * 下发手柄设置。**换输入模式会让 Pico 立刻重启**（输入模式在驱动启动时才应用），
     * 所以调用方拿到 true 之后要自己等设备回来，别再紧接着发下一帧。
     */
    suspend fun padSet(cfg: PadConfig): Boolean = ack(Proto.CMD_GP_SET, cfg.toBytes())

    suspend fun ledGet(): LedConfig? = LedConfig.fromBytes(request(Proto.CMD_LED_GET).payload)

    suspend fun ledSet(cfg: LedConfig): Boolean = ack(Proto.CMD_LED_SET, cfg.toBytes())

    // ---- 蓝牙（设备名 / 配对码 / 开关）----

    /** 改设备名/配对码/开关。返回 false = 参数不合法（不会真的发帧）。 */
    suspend fun btSet(name: String? = null, pairCode: String? = null, btOn: Boolean? = null): Boolean {
        val p = BtSet.payload(name, pairCode, btOn) ?: return false
        return ack(Proto.CMD_BT_SET, p)
    }

    /** 让设备重新生成配对码。返回新的 6 位码；设备随后会踢掉所有手机。 */
    suspend fun btClear(): String {
        val p = request(Proto.CMD_BT_CLEAR).payload
        return String(p, Charsets.US_ASCII)
    }

    // ---- 配置档 ----

    suspend fun profiles(): List<Profiles.Entry>? =
        Profiles.parseList(request(Proto.CMD_PROF_LIST).payload)

    /** 把**设备此刻**的设置存进该档（不是 App 手里那份）。 */
    suspend fun profileSave(slot: Int, name: String = ""): Boolean =
        ack(Proto.CMD_PROF_SAVE, Profiles.savePayload(slot, name))

    /** 加载该档：设备当场改成那份设置并落盘。返回 false = 合法槽位之外的参数。 */
    suspend fun profileLoad(slot: Int): Boolean {
        val p = Profiles.slotPayload(slot) ?: return false
        return ack(Proto.CMD_PROF_LOAD, p)
    }

    suspend fun profileDelete(slot: Int): Boolean {
        val p = Profiles.slotPayload(slot) ?: return false
        return ack(Proto.CMD_PROF_DEL, p)
    }

    /** 只改名字：档里存着的那份设置原样留着（不是拿当前设置重存一遍）。 */
    suspend fun profileRename(slot: Int, name: String): Boolean =
        ack(Proto.CMD_PROF_RENAME, Profiles.savePayload(slot, name))

    /** 固件对 CFG_* 的约定：能把这一帧回出来就算成功（出错会走 CMD_ERR，request() 会抛）。 */
    private suspend fun ack(cmd: Int, payload: ByteArray): Boolean = request(cmd, payload).cmd == cmd

    /**
     * 发任意一条请求帧并等回包（终端页用）。回包走的是同一套 seq 匹配 + 超时 +
     * 错误帧变异常的逻辑，所以终端里看到的"错误 0x04 ..."和别处一致。
     */
    suspend fun sendRequest(cmd: Int, payload: ByteArray = Proto.EMPTY): Frame = request(cmd, payload)
}
