package com.gpcombine.assistant.proto

/** 设备推上来的一行日志（CMD_LOG_EVT）。 */
data class LogEvent(val level: Int, val text: String) {
    /** 落在文件里的一行：时间戳由调用方补，这里只出正文。 */
    fun line(): String = text
}

/**
 * 日志通道的编解码，与固件 `src/net/log_queue.h` + `.ino` 的 logPump 对应：
 *
 *   CMD_LOG_SUB 载荷：mode(1 字节) [+ replay(1 字节)]   0 关 / 1 开 / 2 开且回放
 *   CMD_LOG_EVT 载荷：level(1 字节) + 文本
 *
 * 固件那头行宽上限 96 字节，超过会被截断；这边不做假设，按收到的原文显示。
 */
object LogCodec {
    const val SUB_OFF = 0
    const val SUB_ON = 1
    const val SUB_ON_REPLAY = 2
    const val DEFAULT_REPLAY = 14

    fun subPayload(mode: Int, replay: Int = DEFAULT_REPLAY): ByteArray {
        require(mode in SUB_OFF..SUB_ON_REPLAY) { "未知订阅模式 $mode" }
        return if (mode == SUB_ON_REPLAY) {
            byteArrayOf(mode.toByte(), replay.coerceIn(1, 255).toByte())
        } else {
            byteArrayOf(mode.toByte())
        }
    }

    fun parseEvent(payload: ByteArray): LogEvent? {
        if (payload.isEmpty()) return null
        val level = payload[0].toInt() and 0xFF
        val text = String(payload, 1, payload.size - 1, Charsets.UTF_8)
        return LogEvent(level, text)
    }
}
