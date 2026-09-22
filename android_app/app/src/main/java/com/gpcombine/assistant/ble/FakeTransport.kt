package com.gpcombine.assistant.ble

import com.gpcombine.assistant.proto.Frame
import com.gpcombine.assistant.proto.FrameParser
import com.gpcombine.assistant.proto.EspConfig
import com.gpcombine.assistant.proto.LedConfig
import com.gpcombine.assistant.proto.PadConfig
import com.gpcombine.assistant.proto.Profiles
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
class FakeTransport(pairCode: String = "280148") : BleTransport {
    /** 配对码会被「换码」改掉，所以不是 val。 */
    private var pairCode: String = pairCode
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
    /** 手柄 / 灯光 / 蓝牙 / 配置档：假模式下这几页也能整套试（真机只能靠手机测）。 */
    private var pad: ByteArray = PadConfig().toBytes()
    private var led: ByteArray = LedConfig().toBytes()
    private var btName = "GP-Combine-FAKE"
    private var btOn = true
    private val profiles = mutableMapOf<Int, Pair<String, ByteArray>>()

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
            "name=$btName;pair=$pairCode;bt=${if (btOn) 1 else 0};clients=1;link=2;ap=0".toByteArray(),
        )

        // 手柄 / 灯光：真固件只认正好那么多字节，假设备照抄（和 CFG_* 一个道理）
        req.cmd == Proto.CMD_GP_GET -> Frame(Proto.CMD_GP_GET, req.seq, pad)
        req.cmd == Proto.CMD_GP_SET -> {
            if (req.payload.size == PadConfig.BYTES) pad = req.payload.copyOf()
            Frame(Proto.CMD_GP_SET, req.seq, byteArrayOf(0))
        }

        req.cmd == Proto.CMD_LED_GET -> Frame(Proto.CMD_LED_GET, req.seq, led)
        req.cmd == Proto.CMD_LED_SET -> {
            if (req.payload.size == LedConfig.BYTES) led = req.payload.copyOf()
            Frame(Proto.CMD_LED_SET, req.seq, byteArrayOf(0))
        }

        req.cmd == Proto.CMD_BT_SET -> {
            // 真固件对坏载荷回 ERR_BAD_ARG；假设备同样拒绝，别让测试通过而真机上失败
            val p = req.payload
            if (p.size < 3) {
                err(req.seq, Proto.ERR_BAD_ARG, "bt set arg")
            } else {
                val flags = p[0].toInt() and 0xFF
                if (flags and 0x04 != 0) btOn = (p[1].toInt() and 0xFF) != 0
                val nameLen = p[2].toInt() and 0xFF
                if (flags and 0x01 != 0 && nameLen > 0 && 3 + nameLen <= p.size) {
                    btName = String(p, 3, nameLen, Charsets.UTF_8)
                }
                // 配对码段跟在名字后面；真固件同样会在这里换码（然后踢掉所有手机）
                val pairLenAt = 3 + nameLen
                if (flags and 0x02 != 0 && pairLenAt < p.size) {
                    val pl = p[pairLenAt].toInt() and 0xFF
                    if (pl == 6 && pairLenAt + 1 + pl <= p.size) {
                        pairCode = String(p, pairLenAt + 1, pl, Charsets.US_ASCII)
                    }
                }
                Frame(Proto.CMD_BT_SET, req.seq, byteArrayOf(0))
            }
        }

        req.cmd == Proto.CMD_BT_CLEAR -> {
            pairCode = "135790"      // 真设备是随机生成；假设备固定一个，好断言
            Frame(Proto.CMD_BT_CLEAR, req.seq, pairCode.toByteArray(Charsets.US_ASCII))
        }

        req.cmd == Proto.CMD_PROF_RENAME -> {
            val p = req.payload
            val slot = p.getOrNull(0)?.toInt()?.and(0xFF) ?: 0
            val len = p.getOrNull(1)?.toInt()?.and(0xFF) ?: -1
            val e = profiles[slot]
            if (e == null || len < 0 || 2 + len > p.size) {
                err(req.seq, Proto.ERR_IO, "profile empty")
            } else {
                // 只换名字，存着的那份设置原样留着
                profiles[slot] = String(p, 2, len, Charsets.UTF_8) to e.second
                Frame(Proto.CMD_PROF_RENAME, req.seq, byteArrayOf(0))
            }
        }

        req.cmd == Proto.CMD_PROF_LIST -> {
            val out = ByteArray(Profiles.SLOTS * Profiles.RECORD_BYTES)
            for (i in 1..Profiles.SLOTS) {
                val o = (i - 1) * Profiles.RECORD_BYTES
                val e = profiles[i]
                val nb = (e?.first ?: "").toByteArray(Charsets.UTF_8)
                out[o] = i.toByte()
                out[o + 1] = if (e != null) 1 else 0
                out[o + 2] = nb.size.toByte()
                nb.copyInto(out, o + 3)
            }
            Frame(Proto.CMD_PROF_LIST, req.seq, out)
        }

        req.cmd == Proto.CMD_PROF_SAVE -> {
            val p = req.payload
            val slot = p.getOrNull(0)?.toInt()?.and(0xFF) ?: 0
            val len = p.getOrNull(1)?.toInt()?.and(0xFF) ?: -1
            if (p.size < 2 || slot !in 1..Profiles.SLOTS || len < 0 || 2 + len > p.size) {
                err(req.seq, Proto.ERR_BAD_ARG, "profile arg")
            } else {
                profiles[slot] = String(p, 2, len, Charsets.UTF_8) to cfg.copyOf()
                Frame(Proto.CMD_PROF_SAVE, req.seq, byteArrayOf(0))
            }
        }

        req.cmd == Proto.CMD_PROF_LOAD -> {
            val slot = req.payload.getOrNull(0)?.toInt()?.and(0xFF) ?: 0
            val e = profiles[slot]
            if (e == null) {
                err(req.seq, Proto.ERR_IO, "profile empty")
            } else {
                cfg = e.second.copyOf()
                Frame(Proto.CMD_PROF_LOAD, req.seq, byteArrayOf(0))
            }
        }

        req.cmd == Proto.CMD_PROF_DEL ->
            if (profiles.remove(req.payload.getOrNull(0)?.toInt()?.and(0xFF) ?: 0) == null) {
                err(req.seq, Proto.ERR_IO, "profile absent")
            } else {
                Frame(Proto.CMD_PROF_DEL, req.seq, byteArrayOf(0))
            }

        else -> err(req.seq, Proto.ERR_UNKNOWN_CMD, "unknown cmd")
    }
}
