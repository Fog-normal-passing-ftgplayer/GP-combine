package com.gpcombine.assistant.proto

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * 向量和固件侧 `tools/host_tests/fixes_test.cpp::test_pad_cfg` 是同一组数字：
 * 谁把字节偏移挪了，两套测试里必有一套红。
 */
class PadConfigTest {
    private val pad = PadConfig(
        inputMode = 2,   // PS3
        socdMode = 3,    // 1ST
        dpadMode = 1,    // LAN
        fourWay = 1,
        invertX = 0,
        invertY = 1,
        debounce = 7,
    )

    @Test
    fun padEncodesTheSameVectorAsFirmware() {
        assertArrayEquals(byteArrayOf(2, 3, 1, 0x05, 7), pad.toBytes())
    }

    @Test
    fun padRoundTripsEveryField() {
        val back = PadConfig.fromBytes(pad.toBytes())
        assertEquals(pad, back)
    }

    @Test
    fun padClampsOutOfRangeValues() {
        val wild = PadConfig(
            inputMode = 200, socdMode = 9, dpadMode = 7,
            fourWay = 3, invertX = 2, invertY = 5, debounce = 0,
        )
        val b = wild.toBytes()
        assertEquals(PadConfig.INPUT_MAX, b[0].toInt() and 0xFF)
        assertEquals(4, b[1].toInt() and 0xFF)
        assertEquals(2, b[2].toInt() and 0xFF)
        assertEquals(0x07, b[3].toInt() and 0xFF)
        assertEquals(PadConfig.DEBOUNCE_MIN, b[4].toInt() and 0xFF)
    }

    @Test
    fun padRejectsShortPayload() {
        assertNull(PadConfig.fromBytes(ByteArray(PadConfig.BYTES - 1)))
    }

    private val led = LedConfig(
        animation = 4,
        brightness = 5,
        staticColor = 12,
        turnOffSuspended = 1,
        chaseSpeed = 92,
        rainbowSpeed = 96,
        flowSpeed = 100,
    )

    @Test
    fun ledEncodesTheSameVectorAsFirmware() {
        assertArrayEquals(byteArrayOf(4, 5, 12, 1, 92, 96, 100), led.toBytes())
    }

    @Test
    fun ledRoundTripsEveryField() {
        assertEquals(led, LedConfig.fromBytes(led.toBytes()))
    }

    @Test
    fun ledClampsOutOfRangeValues() {
        val wild = LedConfig(
            animation = 99, brightness = 250, staticColor = 200,
            turnOffSuspended = 0xFF, chaseSpeed = 250, rainbowSpeed = 0, flowSpeed = 101,
        )
        val b = wild.toBytes()
        assertEquals(5, b[0].toInt() and 0xFF)
        assertEquals(5, b[1].toInt() and 0xFF)
        assertEquals(15, b[2].toInt() and 0xFF)
        assertEquals(0x01, b[3].toInt() and 0xFF)
        assertEquals(100, b[4].toInt() and 0xFF)
        assertEquals(0, b[5].toInt() and 0xFF)
        assertEquals(100, b[6].toInt() and 0xFF)
    }

    @Test
    fun ledRejectsShortPayload() {
        assertNull(LedConfig.fromBytes(ByteArray(LedConfig.BYTES - 1)))
    }

    /** 名字数组要和固件 menu 里的 INPUT_NAMES / ANIM_NAMES 对得上：显示"PS3"两边都得是 PS3。 */
    @Test
    fun namesCoverEveryLegalIndex() {
        assertEquals(PadConfig.INPUT_MAX + 1, PadConfig.INPUT_NAMES.size)
        assertEquals(PadConfig.SOCD_MAX + 1, PadConfig.SOCD_NAMES.size)
        assertEquals(PadConfig.DPAD_MAX + 1, PadConfig.DPAD_NAMES.size)
        assertEquals(LedConfig.ANIM_MAX + 1, LedConfig.ANIM_NAMES.size)
        assertEquals(LedConfig.COLOR_MAX + 1, LedConfig.COLOR_NAMES.size)
    }

    /** 输入模式是能重启 Pico 的那一项，App 要据此给"设备重启中"的提示。 */
    @Test
    fun inputModeChangeIsFlagged() {
        assertTrue(pad.copy(inputMode = 5).rebootsDeviceComparedTo(pad))
        assertFalse(pad.copy(debounce = 9).rebootsDeviceComparedTo(pad))
    }

    @Test
    fun speedToCycleMatchesFirmwareTable() {
        assertEquals(1, LedConfig.speedToCycle(100))
        assertEquals(81, LedConfig.speedToCycle(92))
        assertEquals(1001, LedConfig.speedToCycle(0))
        assertEquals(100, LedConfig.cycleToSpeed(1))
        assertEquals(92, LedConfig.cycleToSpeed(81))
        assertEquals(0, LedConfig.cycleToSpeed(1001))
        assertEquals(100, LedConfig.cycleToSpeed(0))
    }
}
