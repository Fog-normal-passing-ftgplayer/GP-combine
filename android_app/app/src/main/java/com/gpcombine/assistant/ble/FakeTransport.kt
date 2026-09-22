package com.gpcombine.assistant.ble

import com.gpcombine.assistant.proto.Frame
import com.gpcombine.assistant.proto.FrameParser
import com.gpcombine.assistant.proto.EspConfig
import com.gpcombine.assistant.proto.Proto
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.MutableSharedFlow

/** 行为照抄固件 netHandleFrame：PING 原样回；AUTH 校验 6 位码；其余没认证回 ERR_NOT_AUTHED。 */
class FakeTransport(private val pairCode: String = "280148") : BleTransport {
    // 用 Channel 而不是 SharedFlow(replay=0)：客户端刚构造、collector 还没被调度时，
    // 假设备立刻回的那一帧不能丢（SharedFlow 无订阅者时是直接丢掉的）。
    private val rx = Channel<Frame>(Channel.UNLIMITED)
    override val inbound: Flow<Frame> = rx.receiveAsFlow()

    private val _state = MutableStateFlow(BleState.IDLE)
    override val state: StateFlow<BleState> = _state.asStateFlow()

    private val _log = MutableSharedFlow<String>(extraBufferCapacity = 32)
    override val log: Flow<String> = _log.asSharedFlow()

    private val _mtu = MutableStateFlow(0)
    override val mtu: StateFlow<Int> = _mtu.asStateFlow()

    private var authed = false
    private var logSub = false
    private var fakeSeq = 0
    /** 假设备也存一份设置镜像：假模式下配置页能整套试，ConfigController 也能在本机跑测试。 */
    private var cfg: ByteArray = EspConfig().toBytes()

    /** 发出去过什么（给测试和"假模式下看看发了啥"用，只留最近 64 条）。 */
    private val sentFrames = ArrayDeque<Frame>()
    fun sent(): List<Frame> = sentFrames.toList()

    fun connect() {
        authed = false
        logSub = false
        _mtu.value = 247
        _state.value = BleState.CONNECTED
        _log.tryEmit("fake: connected")
    }

    /** 订阅之后假设备也要像真设备那样主动推日志，否则诊断页在假模式下是空的。 */
    private fun fakeLog(line: String) {
        if (!logSub) return
        rx.trySend(
            Frame(Proto.CMD_LOG_EVT, 0, byteArrayOf(0) + line.toByteArray(Charsets.UTF_8))
        )
    }

    override suspend fun send(frame: ByteArray) {
        val parser = FrameParser()
        var req: Frame? = null
        for (b in frame) {
            val f = parser.push(b)
            if (f != null) {
                req = f
                break
            }
        }
        req?.let {
            sentFrames.addLast(it)
            if (sentFrames.size > 64) sentFrames.removeFirst()
        }
        rx.trySend(reply(req ?: return))
    }

    private fun err(seq: Int, code: Int, text: String) =
        Frame(Proto.CMD_ERR, seq, byteArrayOf(code.toByte()) + text.toByteArray())

    private fun reply(req: Frame): Frame = when {
        req.cmd == Proto.CMD_AUTH -> {
            val ok = String(req.payload, Charsets.US_ASCII) == pairCode
            if (ok) authed = true
            Frame(Proto.CMD_AUTH, req.seq, byteArrayOf(if (ok) 1 else 0))
        }

        req.cmd == Proto.CMD_PING -> {          // 探活免认证，和固件一致
            fakeSeq++
            if (fakeSeq % 5 == 0) fakeLog("[fake] fps=42.0 heap_int=67056")
            Frame(Proto.CMD_PING, req.seq, req.payload)
        }

        !authed -> err(req.seq, Proto.ERR_NOT_AUTHED, "auth first")

        req.cmd == Proto.CMD_LOG_SUB -> {
            logSub = req.payload.isNotEmpty() && req.payload[0].toInt() != 0
            if (logSub) {
                // 回放：真设备会推最近 N 行，这里给两条固定样本
                fakeLog("[fake] 这是回放的第 1 行")
                fakeLog("[fake] 这是回放的第 2 行")
            }
            Frame(Proto.CMD_LOG_SUB, req.seq, byteArrayOf(1))
        }

        req.cmd == Proto.CMD_INFO -> Frame(
            Proto.CMD_INFO, req.seq,
            "ver=0.0.0-fake;app=825776;fs=12517376/2540000;ram=67056;psram=5588080".toByteArray(),
        )

        req.cmd == Proto.CMD_CFG_GET -> Frame(Proto.CMD_CFG_GET, req.seq, cfg)

        req.cmd == Proto.CMD_CFG_APPLY || req.cmd == Proto.CMD_CFG_SET -> {
            // 真固件只接受正好 17 字节；假设备照抄这条，免得测试里漏掉长度 bug
            if (req.payload.size == EspConfig.BYTES) cfg = req.payload.copyOf()
            Frame(req.cmd, req.seq, byteArrayOf(0))
        }

        req.cmd == Proto.CMD_CFG_RESET -> {
            cfg = EspConfig().toBytes()
            Frame(Proto.CMD_CFG_RESET, req.seq, byteArrayOf(0))
        }

        req.cmd == Proto.CMD_PAIR_INFO -> Frame(
            Proto.CMD_PAIR_INFO, req.seq,
            "name=GP-Combine-FAKE;pair=$pairCode;bt=1;clients=1;ap=0".toByteArray(),
        )

        else -> err(req.seq, Proto.ERR_UNKNOWN_CMD, "unknown cmd")
    }
}
