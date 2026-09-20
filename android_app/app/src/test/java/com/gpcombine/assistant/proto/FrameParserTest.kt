package com.gpcombine.assistant.proto

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

class FrameParserTest {
    private fun hex(s: String) = s.trim().split(" ").map { it.toInt(16).toByte() }.toByteArray()

    private fun feed(p: FrameParser, bytes: ByteArray): List<Frame> {
        val out = mutableListOf<Frame>()
        for (b in bytes) p.push(b)?.let { out += it }
        return out
    }

    @Test
    fun parsesSingleFrame() {
        val got = feed(FrameParser(), hex("A5 5A 01 01 00 00 00 00 E1 E1"))
        assertEquals(1, got.size)
        assertEquals(Proto.CMD_PING, got[0].cmd)
        assertEquals(0, got[0].seq)
        assertEquals(0, got[0].payload.size)
    }

    /** MTU 23 时 INFO 回包会被切成 20 字节一片，逐片喂进来必须只吐一帧。 */
    @Test
    fun reassemblesFragmentedFrame() {
        val payload = "ver=a;app=1;fs=2/3;ram=4;psram=5".toByteArray()
        val frame = Proto.build(Proto.CMD_INFO, 7, payload)
        val p = FrameParser()
        val got = mutableListOf<Frame>()
        var off = 0
        while (off < frame.size) {
            val chunk = Proto.notifyChunk(23, frame.size - off)
            for (i in off until off + chunk) p.push(frame[i])?.let { got += it }
            off += chunk
            // 分片中间绝不能提前吐帧
            if (off < frame.size) assertEquals("分片中途不该出帧", 0, got.size)
        }
        assertEquals(1, got.size)
        assertEquals(Proto.CMD_INFO, got[0].cmd)
        assertEquals(7, got[0].seq)
        assertEquals(String(payload), String(got[0].payload))
    }

    @Test
    fun dropsGarbageAndResyncs() {
        // 前面 3 个坏字节 + 后面一帧，必须还能认出那一帧
        val bytes = hex("00 FF A5") + hex("A5 5A 01 01 00 00 00 00 E1 E1")
        val got = feed(FrameParser(), bytes)
        assertEquals("坏字节后应重新同步", 1, got.size)
        assertEquals(Proto.CMD_PING, got[0].cmd)
    }

    @Test
    fun rejectsBadCrc() {
        // 把 CRC 最后一字节改掉
        val bad = hex("A5 5A 01 01 00 00 00 00 E1 E0")
        assertNull("CRC 不对不能吐帧", feed(FrameParser(), bad).firstOrNull())
    }

    @Test
    fun rejectsOversizedLength() {
        // len=0x0200=512 > MAX_PAYLOAD(256)，应当丢掉而不是等 512 字节
        val bytes = hex("A5 5A 01 01 00 00 00 02")
        assertNull(feed(FrameParser(), bytes).firstOrNull())
    }

    @Test
    fun parsesTwoFramesInOneStream() {
        val stream = Proto.build(Proto.CMD_PING, 1) + Proto.build(Proto.CMD_CFG_GET, 2)
        val got = feed(FrameParser(), stream)
        assertEquals(2, got.size)
        assertEquals(Proto.CMD_PING, got[0].cmd)
        assertEquals(Proto.CMD_CFG_GET, got[1].cmd)
    }

    @Test
    fun resetClearsHalfFrame() {
        val p = FrameParser()
        feed(p, hex("A5 5A 01 01 00 00 00 00 E1"))
        p.reset()
        assertNotNull(feed(p, hex("A5 5A 01 01 00 00 00 00 E1 E1"))[0])
    }
}
