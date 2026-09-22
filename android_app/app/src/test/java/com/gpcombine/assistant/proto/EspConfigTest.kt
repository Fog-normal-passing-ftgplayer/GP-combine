package com.gpcombine.assistant.proto

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * 向量和固件侧 `tools/host_tests/fixes_test.cpp::test_esp_cfg` 是同一组数字：
 * 谁把字节偏移挪了，两套测试里必有一套红。
 */
class EspConfigTest {
    private val sample = EspConfig(
        inputHistory = 1,
        layout = 2,
        bgOpacity = 3,
        backlight = 55,
        flipX = 1,
        flipY = 0,
        invert = 0,
        saverMode = 4,
        saverSecs = 300,
        screenOff = 1,
        wireless = 0,
        theme = 6,
        style = 2,
    )

    private val sampleBytes = byteArrayOf(
        1, 1, 1, 2, 3, 55, 1, 0, 0, 4,
        0x2C, 0x01, 1, 0, 6, 2, 0,
    )

    @Test
    fun encodesTheSameVectorAsFirmware() {
        assertArrayEquals(sampleBytes, sample.toBytes())
    }

    @Test
    fun roundTripsEveryField() {
        val back = EspConfig.fromBytes(sampleBytes)!!
        assertEquals(1, back.inputHistory)
        assertEquals(2, back.layout)
        assertEquals(3, back.bgOpacity)
        assertEquals(55, back.backlight)
        assertEquals(1, back.flipX)
        assertEquals(0, back.flipY)
        assertEquals(0, back.invert)
        assertEquals(4, back.saverMode)
        assertEquals(300, back.saverSecs)
        assertEquals(1, back.screenOff)
        assertEquals(0, back.wireless)
        assertEquals(6, back.theme)
        assertEquals(2, back.style)
    }

    /** 屏保时间是 24 位里唯一的多字节字段，往返错位过一次（u16 被截成 u8）就靠这条兜住。 */
    @Test
    fun saverSecondsSurviveTheTwoByteField() {
        assertArrayEquals(
            byteArrayOf(0x2C, 0x01),
            EspConfig(saverSecs = 300).toBytes().copyOfRange(10, 12),
        )
        assertEquals(600, EspConfig.fromBytes(EspConfig(saverSecs = 600).toBytes())!!.saverSecs)
        assertEquals(0, EspConfig.fromBytes(EspConfig(saverSecs = 0).toBytes())!!.saverSecs)
    }

    @Test
    fun clampsOutOfRangeValues() {
        val wild = EspConfig(
            inputHistory = 9, layout = 200, bgOpacity = 99, backlight = 250,
            flipX = 7, saverMode = 42, saverSecs = 60000, theme = 250, style = 9,
        ).clamp()
        assertEquals(1, wild.inputHistory)
        assertEquals(EspConfig.LAYOUT_MAX, wild.layout)
        assertEquals(EspConfig.OPACITY_MAX, wild.bgOpacity)
        assertEquals(100, wild.backlight)
        assertEquals(1, wild.flipX)
        assertEquals(EspConfig.SAVER_MODE_MAX, wild.saverMode)
        assertEquals(EspConfig.SAVER_SECS_MAX, wild.saverSecs)
        assertEquals(EspConfig.THEME_MAX, wild.theme)
        assertEquals(EspConfig.STYLE_MAX, wild.style)
        // 越界值也不许逃进字节流
        val b = EspConfig(theme = 250, style = 9, backlight = 250).toBytes()
        assertEquals(EspConfig.THEME_MAX, b[14].toInt())
        assertEquals(EspConfig.STYLE_MAX, b[15].toInt())
        assertEquals(100, b[5].toInt())
    }

    @Test
    fun usesTheSameDefaultsAsFirmware() {
        val d = EspConfig()
        assertEquals(EspConfig.DEFAULT_LAYOUT, d.layout)
        assertEquals(1, d.bgOpacity)
        assertEquals(100, d.backlight)
        assertEquals(1, d.saverMode)
        assertEquals(60, d.saverSecs)
        assertEquals(1, d.screenOff)
        assertEquals(1, d.wireless)
        assertEquals(0, d.theme)
        assertEquals(0, d.style)
        assertEquals(0, d.inputHistory)
    }

    @Test
    fun rejectsShortOrMismatchedMirrors() {
        assertNull("短一字节不是镜像", EspConfig.fromBytes(sampleBytes.copyOf(16)))
        val wrongFormat = sampleBytes.copyOf().also { it[1] = 99 }
        assertNull("格式版本不对", EspConfig.fromBytes(wrongFormat))
        val wrongMagic = sampleBytes.copyOf().also { it[0] = 0 }
        assertNull("magic 不对", EspConfig.fromBytes(wrongMagic))
    }

    @Test
    fun dirtyDetectsRealChangesOnly() {
        val a = EspConfig()
        assertEquals(true, a.sameAs(EspConfig()))
        assertEquals(false, a.sameAs(EspConfig(theme = 5)))
        // 越界值钳过之后一样，就不该算"改了"
        assertEquals(true, EspConfig(theme = 99).sameAs(EspConfig(theme = EspConfig.THEME_MAX)))
    }
}
