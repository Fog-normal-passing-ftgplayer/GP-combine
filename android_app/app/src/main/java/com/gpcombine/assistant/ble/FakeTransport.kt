package com.gpcombine.assistant.ble

import com.gpcombine.assistant.proto.Frame
import com.gpcombine.assistant.proto.FrameParser
import com.gpcombine.assistant.proto.Proto
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.receiveAsFlow

/** 行为照抄固件 netHandleFrame：PING 原样回；AUTH 校验 6 位码；其余没认证回 ERR_NOT_AUTHED。 */
class FakeTransport(private val pairCode: String = "280148") : BleTransport {
    // 用 Channel 而不是 SharedFlow(replay=0)：客户端刚构造、collector 还没被调度时，
    // 假设备立刻回的那一帧不能丢（SharedFlow 无订阅者时是直接丢掉的）。
    private val rx = Channel<Frame>(Channel.UNLIMITED)
    override val inbound: Flow<Frame> = rx.receiveAsFlow()

    private val _state = MutableStateFlow(BleState.IDLE)
    override val state: StateFlow<BleState> = _state.asStateFlow()

    private var authed = false

    fun connect() {
        authed = false
        _state.value = BleState.CONNECTED
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
        rx.trySend(reply(req ?: return))
    }

    private fun err(seq: Int, code: Int, text: String) =
        Frame(Proto.CMD_ERR, seq, byteArrayOf(code.toByte()) + text.toByteArray())

    private fun reply(req: Frame): Frame = when {
        req.cmd == Proto.CMD_PING -> Frame(Proto.CMD_PING, req.seq, req.payload)

        req.cmd == Proto.CMD_AUTH -> {
            val ok = String(req.payload, Charsets.US_ASCII) == pairCode
            if (ok) authed = true
            Frame(Proto.CMD_AUTH, req.seq, byteArrayOf(if (ok) 1 else 0))
        }

        !authed -> err(req.seq, Proto.ERR_NOT_AUTHED, "auth first")

        req.cmd == Proto.CMD_INFO -> Frame(
            Proto.CMD_INFO, req.seq,
            "ver=0.0.0-fake;app=825776;fs=12517376/2540000;ram=67056;psram=5588080".toByteArray(),
        )

        req.cmd == Proto.CMD_PAIR_INFO -> Frame(
            Proto.CMD_PAIR_INFO, req.seq,
            "name=GP-Combine-FAKE;pair=$pairCode;bt=1;clients=1;ap=0".toByteArray(),
        )

        else -> err(req.seq, Proto.ERR_UNKNOWN_CMD, "unknown cmd")
    }
}
