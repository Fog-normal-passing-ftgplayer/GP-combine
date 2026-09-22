package com.gpcombine.assistant.proto

/**
 * 17 字节「ESP 配置镜像」。
 *
 * 布局逐字节对齐固件 `esp32_170x320/src/net/esp_cfg.h`，而且两边用**同一组测试向量**
 * （固件侧 `tools/host_tests/fixes_test.cpp` 的 `test_esp_cfg`，App 侧 `EspConfigTest`）：
 * 谁把偏移挪了，两套测试里必有一套红。改这里必须同时改 esp_cfg.h 和那两个测试。
 *
 * 名字数组也和固件里的 THEME_NAMES / STYLE_NAMES / SAVER_NAMES / LAYOUT_NAMES /
 * BG_LEVEL_NAMES 保持一致——App 里显示"翠绿"而设备上显示"翠绿"，对得上号才能排查。
 */
data class EspConfig(
    val inputHistory: Int = 0,
    val layout: Int = DEFAULT_LAYOUT,
    val bgOpacity: Int = 1,
    val backlight: Int = 100,
    val flipX: Int = 0,
    val flipY: Int = 0,
    val invert: Int = 0,
    val saverMode: Int = 1,
    val saverSecs: Int = 60,
    val screenOff: Int = 1,
    val wireless: Int = 1,
    val theme: Int = 0,
    val style: Int = 0,
) {
    /** 有没有和另一份快照不同（用来算 dirty）。 */
    fun sameAs(o: EspConfig): Boolean = clamp() == o.clamp()

    /** 越界值一律钳回范围：宁可显示成"被夹过的值"，也不要设备端出现乱码选项。 */
    fun clamp(): EspConfig = copy(
        inputHistory = inputHistory.coerceIn(0, 1),
        layout = layout.coerceIn(0, LAYOUT_MAX),
        bgOpacity = bgOpacity.coerceIn(0, OPACITY_MAX),
        backlight = backlight.coerceIn(0, 100),
        flipX = flipX.coerceIn(0, 1),
        flipY = flipY.coerceIn(0, 1),
        invert = invert.coerceIn(0, 1),
        saverMode = saverMode.coerceIn(0, SAVER_MODE_MAX),
        saverSecs = saverSecs.coerceIn(0, SAVER_SECS_MAX),
        screenOff = screenOff.coerceIn(0, 1),
        wireless = wireless.coerceIn(0, 1),
        theme = theme.coerceIn(0, THEME_MAX),
        style = style.coerceIn(0, STYLE_MAX),
    )

    fun toBytes(): ByteArray {
        val c = clamp()
        val out = ByteArray(BYTES)
        out[0] = MAGIC.toByte()
        out[1] = FORMAT.toByte()
        out[2] = c.inputHistory.toByte()
        out[3] = c.layout.toByte()
        out[4] = c.bgOpacity.toByte()
        out[5] = c.backlight.toByte()
        out[6] = c.flipX.toByte()
        out[7] = c.flipY.toByte()
        out[8] = c.invert.toByte()
        out[9] = c.saverMode.toByte()
        out[10] = (c.saverSecs and 0xFF).toByte()
        out[11] = ((c.saverSecs shr 8) and 0xFF).toByte()
        out[12] = c.screenOff.toByte()
        out[13] = c.wireless.toByte()
        out[14] = c.theme.toByte()
        out[15] = c.style.toByte()
        out[16] = 0
        return out
    }

    companion object {
        const val BYTES = 17
        const val MAGIC = 1
        const val FORMAT = 1
        const val DEFAULT_LAYOUT = 1

        const val LAYOUT_MAX = 3
        const val OPACITY_MAX = 4
        const val SAVER_MODE_MAX = 6
        const val SAVER_SECS_MAX = 600
        const val THEME_MAX = 9
        const val STYLE_MAX = 2

        /** 和设备菜单同名同序，别改顺序（改了老设备的索引就错位）。 */
        val LAYOUT_NAMES = listOf("街机", "HITBOX", "WASD", "自定义")
        val THEME_NAMES = listOf(
            "默认", "品牌橙", "绯红", "翠绿", "紫罗兰", "青蓝", "浅色", "背景图", "中性", "纯黑",
        )
        val STYLE_NAMES = listOf("无", "复古扫描线", "暗角")
        val SAVER_NAMES = listOf("关闭", "雪花", "弹跳", "管道", "吐司", "MATRIX", "GIF")
        val OPACITY_NAMES = listOf("25%", "40%", "55%", "70%", "85%")

        /** 长度/版本/magic 任一对不上就返回 null（调用方据此走"当作没读到"）。 */
        fun fromBytes(b: ByteArray): EspConfig? {
            if (b.size < BYTES) return null
            if ((b[0].toInt() and 0xFF) != MAGIC || (b[1].toInt() and 0xFF) != FORMAT) return null
            fun u(i: Int) = b[i].toInt() and 0xFF
            return EspConfig(
                inputHistory = u(2),
                layout = u(3),
                bgOpacity = u(4),
                backlight = u(5),
                flipX = u(6),
                flipY = u(7),
                invert = u(8),
                saverMode = u(9),
                saverSecs = u(10) or (u(11) shl 8),
                screenOff = u(12),
                wireless = u(13),
                theme = u(14),
                style = u(15),
            ).clamp()
        }
    }
}
