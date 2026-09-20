package com.gpcombine.assistant.net

import com.gpcombine.assistant.ble.BleTransport
import com.gpcombine.assistant.proto.DeviceInfo
import com.gpcombine.assistant.proto.Frame
import com.gpcombine.assistant.proto.InfoCodec
import com.gpcombine.assistant.proto.PairInfo
import com.gpcombine.assistant.proto.Proto
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
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
) {
    private val pending = mutableMapOf<Int, CompletableDeferred<Frame>>()
    private val lock = Mutex()
    private var nextSeq = 0

    private val collector: Job = scope.launch {
        transport.inbound.collect { onFrame(it) }
    }

    fun close() {
        collector.cancel()
        pending.values.forEach { it.cancel() }
        pending.clear()
    }

    private fun onFrame(f: Frame) {
        val d = pending[f.seq] ?: return
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
            transport.send(Proto.build(cmd, seq, payload))
            withTimeout(timeoutMs) { d.await() }
        } finally {
            pending.remove(seq)
        }
    }

    suspend fun ping(): Boolean = request(Proto.CMD_PING).cmd == Proto.CMD_PING

    suspend fun auth(code: String): Boolean {
        val f = request(Proto.CMD_AUTH, code.toByteArray(Charsets.US_ASCII))
        return f.payload.isNotEmpty() && f.payload[0].toInt() == 1
    }

    suspend fun info(): DeviceInfo =
        InfoCodec.parseInfo(String(request(Proto.CMD_INFO).payload, Charsets.US_ASCII))

    suspend fun pairInfo(): PairInfo =
        InfoCodec.parsePairInfo(String(request(Proto.CMD_PAIR_INFO).payload, Charsets.US_ASCII))
}
