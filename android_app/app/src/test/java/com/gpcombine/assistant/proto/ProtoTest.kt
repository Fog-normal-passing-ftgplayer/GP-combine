package com.gpcombine.assistant.proto

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Test

class ProtoTest {
    private fun hex(s: String) = s.trim().split(" ").map { it.toInt(16).toByte() }.toByteArray()

    @Test
    fun crcMatchesFirmware() {
        assertEquals("PING 帧的 CRC", 0xE1E1, Proto.crc16(hex("01 01 00 00 00 00")))
        assertEquals(
            "AUTH(seq=0) 帧的 CRC",
            0xAD8D,
            Proto.crc16(hex("01 02 00 00 06 00 32 38 30 31 34 38")),
        )
    }

    @Test
    fun buildMatchesDeviceLog() {
        assertArrayEquals(
            hex("A5 5A 01 01 00 00 00 00 E1 E1"),
            Proto.build(Proto.CMD_PING, 0),
        )
        assertArrayEquals(
            hex("A5 5A 01 02 01 00 06 00 32 38 30 31 34 38 C8 C2"),
            Proto.build(Proto.CMD_AUTH, 1, "280148".toByteArray()),
        )
        assertArrayEquals(hex("A5 5A 01 03 02 00 00 00 0A 48"), Proto.build(Proto.CMD_INFO, 2))
        assertArrayEquals(hex("A5 5A 01 04 03 00 00 00 6A 59"), Proto.build(Proto.CMD_PAIR_INFO, 3))
        assertArrayEquals(hex("A5 5A 01 10 04 00 00 00 1B 85"), Proto.build(Proto.CMD_CFG_GET, 4))
    }

    @Test
    fun notifyChunkMatchesFirmware() {
        assertEquals(244, Proto.notifyChunk(247, 250))
        assertEquals(20, Proto.notifyChunk(23, 250))
        assertEquals(182, Proto.notifyChunk(185, 250))
        assertEquals(10, Proto.notifyChunk(247, 10))
        assertEquals(10, Proto.notifyChunk(0, 10))
        assertEquals(20, Proto.notifyChunk(0, 250))
    }

    @Test
    fun seqIsLittleEndian() {
        assertEquals(0x34, Proto.build(Proto.CMD_PING, 0x1234)[4].toInt() and 0xFF)
        assertEquals(0x12, Proto.build(Proto.CMD_PING, 0x1234)[5].toInt() and 0xFF)
    }
}
