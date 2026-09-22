package com.gpcombine.assistant.proto

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class LogCodecTest {
    @Test
    fun parsesLevelAndText() {
        val payload = byteArrayOf(0) + "[ble] clients=1".toByteArray(Charsets.UTF_8)
        val e = LogCodec.parseEvent(payload)!!
        assertEquals(0, e.level)
        assertEquals("[ble] clients=1", e.text)
    }

    @Test
    fun keepsUtf8ChineseIntact() {
        val text = "[dbg] 屏幕又不亮了"
        val e = LogCodec.parseEvent(byteArrayOf(1) + text.toByteArray(Charsets.UTF_8))!!
        assertEquals(text, e.text)
    }

    @Test
    fun rejectsEmptyPayload() {
        assertNull("空载荷不是一帧日志", LogCodec.parseEvent(ByteArray(0)))
    }

    @Test
    fun subPayloadMatchesFirmwareLayout() {
        assertEquals(1, LogCodec.subPayload(LogCodec.SUB_OFF).size)
        assertEquals(0, LogCodec.subPayload(LogCodec.SUB_OFF)[0].toInt())
        assertEquals(1, LogCodec.subPayload(LogCodec.SUB_ON).size)
        val replay = LogCodec.subPayload(LogCodec.SUB_ON_REPLAY, 32)
        assertEquals(2, replay.size)
        assertEquals(2, replay[0].toInt())
        assertEquals(32, replay[1].toInt())
        // 回放行数 0 没有意义，夹到 1（固件侧同样会回退成默认值）
        assertEquals(1, LogCodec.subPayload(LogCodec.SUB_ON_REPLAY, 0)[1].toInt())
    }
}
