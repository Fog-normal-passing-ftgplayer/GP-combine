package com.gpcombine.assistant.net

enum class Dir { TX, RX }

/**
 * 帧监视器的一条记录：等于把串口终端里那两行 `[ble] rx cmd=..` / 发帧记录搬进 App。
 * HEX 只留前 [MAX_HEX] 字节 —— 一帧最多 266 字节，全展开在列表里没法看，够定位就行。
 */
data class FrameRecord(
    val dir: Dir,
    val timeMs: Long,
    val cmd: Int,
    val seq: Int,
    val payload: ByteArray,
    val note: String = "",
) {
    val len: Int get() = payload.size

    val hex: String
        get() {
            if (payload.isEmpty()) return ""
            val head = payload.take(MAX_HEX).joinToString(" ") { String.format("%02X", it) }
            return if (payload.size > MAX_HEX) "$head …(${payload.size}B)" else head
        }

    val text: String
        get() = payload.takeIf { it.isNotEmpty() }?.let { String(it, Charsets.UTF_8) } ?: ""

    companion object {
        const val MAX_HEX = 24

        fun cmdName(cmd: Int): String = when (cmd) {
            0x01 -> "PING"
            0x02 -> "AUTH"
            0x03 -> "INFO"
            0x04 -> "PAIR_INFO"
            0x06 -> "LOG_SUB"
            0x10 -> "CFG_GET"
            0x11 -> "CFG_SET"
            0x12 -> "CFG_RESET"
            0x7F -> "ERR"
            0x86 -> "LOG_EVT"
            else -> String.format("0x%02X", cmd)
        }
    }

    override fun equals(other: Any?): Boolean =
        other is FrameRecord && dir == other.dir && timeMs == other.timeMs && cmd == other.cmd &&
            seq == other.seq && payload.contentEquals(other.payload) && note == other.note

    override fun hashCode(): Int =
        (((dir.hashCode() * 31 + timeMs.hashCode()) * 31 + cmd) * 31 + seq) * 31 + payload.contentHashCode()
}
