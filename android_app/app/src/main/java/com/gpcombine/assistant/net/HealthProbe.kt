package com.gpcombine.assistant.net

import com.gpcombine.assistant.proto.DeviceInfo
import com.gpcombine.assistant.proto.Proto
import kotlinx.coroutines.TimeoutCancellationException

/**
 * 一键体检的结果。
 *
 * `infoChunks` 是按当前 MTU **算**出来的，不是设备报的：固件只在 BLE 层分片，协议层
 * 看不到"这一帧分了几片"。显示时要说清楚是估算，别让人以为是实测。
 */
data class HealthReport(
    val rounds: Int,
    val ok: Int,
    val minMs: Long,
    val avgMs: Long,
    val maxMs: Long,
    val mtu: Int,
    val infoBytes: Int,
    val infoChunks: Int,
    val info: DeviceInfo?,
) {
    val lost: Int get() = rounds - ok
}

/**
 * 体检：PING 若干轮取延迟，再看一眼 INFO 回包大小和协商到的 MTU。
 * 这几样正好覆盖"能连上但用起来别扭"的三种典型病因：延迟高、MTU 没协商上去（帧被打成很多片）、
 * 设备内存紧张。
 */
class HealthProbe(
    private val client: DeviceClient,
    private val mtu: () -> Int,
    private val clock: () -> Long = { System.currentTimeMillis() },
) {
    suspend fun run(rounds: Int = 20): HealthReport {
        val n = rounds.coerceIn(1, 200)
        var ok = 0
        var min = Long.MAX_VALUE
        var max = 0L
        var sum = 0L

        repeat(n) {
            val t0 = clock()
            val answered = try {
                client.ping()
            } catch (e: TimeoutCancellationException) {
                false
            } catch (e: DeviceException) {
                false
            }
            if (answered) {
                val dt = (clock() - t0).coerceAtLeast(0)
                ok++
                sum += dt
                if (dt < min) min = dt
                if (dt > max) max = dt
            }
        }

        // runCatching 而不是 try/catch 赋给 val：Kotlin 不允许在 try 和 catch 里各赋一次
        val raw = runCatching { client.infoRaw() }.getOrNull()
        val infoBytes = raw?.size ?: 0
        val info = if (raw != null) runCatching { client.info() }.getOrNull() else null

        val m = mtu()
        val chunk = Proto.notifyChunk(m, Int.MAX_VALUE)
        val frameBytes = Proto.HEADER + infoBytes + 2
        val chunks = if (infoBytes > 0 && chunk > 0) (frameBytes + chunk - 1) / chunk else 0

        return HealthReport(
            rounds = n,
            ok = ok,
            minMs = if (ok > 0) min else 0,
            avgMs = if (ok > 0) sum / ok else 0,
            maxMs = max,
            mtu = m,
            infoBytes = infoBytes,
            infoChunks = chunks,
            info = info,
        )
    }
}
