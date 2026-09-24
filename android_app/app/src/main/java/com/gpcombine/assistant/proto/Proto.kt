package com.gpcombine.assistant.proto

/**
 * 帧格式，与固件 esp32_170x320/src/net/proto.h 逐字对应，改一边必须改另一边。
 *
 *   A5 5A | ver=1 | cmd | seq(LE) | len(LE) | payload | CRC16-CCITT(LE，覆盖 ver..payload)
 */
object Proto {
    const val MAGIC0 = 0xA5
    const val MAGIC1 = 0x5A
    const val VERSION = 1
    const val HEADER = 8
    const val MAX_PAYLOAD = 256

    /** BLE 单次 notify/写 的 ATT 头占 3 字节 */
    private const val ATT_HEADER = 3

    const val CMD_PING = 0x01
    const val CMD_AUTH = 0x02
    const val CMD_INFO = 0x03
    const val CMD_PAIR_INFO = 0x04
    const val CMD_LOG_SUB = 0x06
    const val CMD_CFG_GET = 0x10
    const val CMD_CFG_SET = 0x11
    const val CMD_CFG_RESET = 0x12
    const val CMD_CFG_APPLY = 0x13
    const val CMD_ERR = 0x7F

    /** 设备主动推的事件（不带 seq，不能拿它等回包） */
    const val CMD_LOG_EVT = 0x86

    fun isDevicePush(cmd: Int): Boolean = cmd >= 0x80

    const val ERR_OK = 0x00
    const val ERR_BAD_CRC = 0x01
    const val ERR_BAD_LEN = 0x02
    const val ERR_UNKNOWN_CMD = 0x03
    const val ERR_NOT_AUTHED = 0x04

    val EMPTY = ByteArray(0)

    /** CRC16-CCITT：初值 0xFFFF、多项式 0x1021、不反转 */
    fun crc16(data: ByteArray, from: Int = 0, until: Int = data.size): Int {
        var crc = 0xFFFF
        for (i in from until until) {
            crc = crc xor ((data[i].toInt() and 0xFF) shl 8)
            repeat(8) {
                crc = if (crc and 0x8000 != 0) ((crc shl 1) xor 0x1021) else (crc shl 1)
                crc = crc and 0xFFFF
            }
        }
        return crc
    }

    fun build(cmd: Int, seq: Int, payload: ByteArray = EMPTY): ByteArray {
        require(payload.size <= MAX_PAYLOAD) { "载荷 ${payload.size} 字节，超过 $MAX_PAYLOAD" }
        val out = ByteArray(HEADER + payload.size + 2)
        out[0] = MAGIC0.toByte()
        out[1] = MAGIC1.toByte()
        out[2] = VERSION.toByte()
        out[3] = cmd.toByte()
        out[4] = (seq and 0xFF).toByte()
        out[5] = ((seq ushr 8) and 0xFF).toByte()
        out[6] = (payload.size and 0xFF).toByte()
        out[7] = ((payload.size ushr 8) and 0xFF).toByte()
        payload.copyInto(out, HEADER)
        val crc = crc16(out, 2, HEADER + payload.size)
        out[HEADER + payload.size] = (crc and 0xFF).toByte()
        out[HEADER + payload.size + 1] = ((crc ushr 8) and 0xFF).toByte()
        return out
    }

    /** 一次 notify 最多带多少字节。MTU 未知(0) 时退到 BLE 最小 MTU 23 → 20 字节。 */
    fun notifyChunk(mtu: Int, remaining: Int): Int {
        val m = if (mtu > ATT_HEADER) mtu - ATT_HEADER else 20
        return if (remaining < m) remaining else m
    }
}
