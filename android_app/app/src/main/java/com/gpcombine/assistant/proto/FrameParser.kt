package com.gpcombine.assistant.proto

data class Frame(val cmd: Int, val seq: Int, val payload: ByteArray) {
    override fun equals(other: Any?): Boolean =
        other is Frame && cmd == other.cmd && seq == other.seq && payload.contentEquals(other.payload)

    override fun hashCode(): Int = (cmd * 31 + seq) * 31 + payload.contentHashCode()
}

/**
 * 增量收帧器，算法与固件 proto.h 的 ProtoRx::tryParse 一致：只认队首那一帧；
 * 魔数、长度、CRC 任何一处不对就把队首挪掉一格重找，所以混进垃圾或半个残帧也能自己走回来。
 */
class FrameParser {
    private val buf = ByteArray(Proto.HEADER + Proto.MAX_PAYLOAD + 2)
    private var have = 0

    fun reset() {
        have = 0
    }

    fun push(b: Byte): Frame? {
        if (have >= buf.size) dropFront(1)
        buf[have++] = b
        return tryParse()
    }

    private fun dropFront(n: Int) {
        System.arraycopy(buf, n, buf, 0, have - n)
        have -= n
    }

    private fun tryParse(): Frame? {
        while (true) {
            if (have < 2) return null
            if (buf[0] != Proto.MAGIC0.toByte() || buf[1] != Proto.MAGIC1.toByte()) {
                dropFront(1)
                continue
            }
            if (have < Proto.HEADER) return null

            val len = (buf[6].toInt() and 0xFF) or ((buf[7].toInt() and 0xFF) shl 8)
            if (len > Proto.MAX_PAYLOAD) {
                dropFront(1)
                continue
            }
            val total = Proto.HEADER + len + 2
            if (have < total) return null

            val crcRx = (buf[total - 2].toInt() and 0xFF) or ((buf[total - 1].toInt() and 0xFF) shl 8)
            val crcCalc = Proto.crc16(buf, 2, Proto.HEADER + len)
            if (crcRx != crcCalc) {
                dropFront(1)
                continue
            }

            val frame = Frame(
                cmd = buf[3].toInt() and 0xFF,
                seq = (buf[4].toInt() and 0xFF) or ((buf[5].toInt() and 0xFF) shl 8),
                payload = buf.copyOfRange(Proto.HEADER, Proto.HEADER + len),
            )
            dropFront(total)
            return frame
        }
    }
}
