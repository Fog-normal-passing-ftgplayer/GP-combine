package com.gpcombine.assistant.proto

/**
 * 手柄设置（5 字节）。布局逐字节对齐固件 `esp32_170x320/src/net/pad_cfg.h`，
 * 两边用**同一组测试向量**（固件 `fixes_test.cpp::test_pad_cfg` / 这里 `PadConfigTest`）。
 *
 * 单位是设备菜单的单位（枚举索引、毫秒），不是发给 Pico 那帧的原始字节 ——
 * App 上写 7ms 去抖就是菜单里的 7ms，中间不再多一次换算。
 *
 * 注意：改 [inputMode] 会让 Pico 自己重启（输入模式在驱动启动时应用），
 * 所以这一页不做"边改边下发"，必须点「应用到设备」。
 */
data class PadConfig(
    val inputMode: Int = 0,
    val socdMode: Int = 0,
    val dpadMode: Int = 0,
    val fourWay: Int = 0,
    val invertX: Int = 0,
    val invertY: Int = 0,
    val debounce: Int = 5,
) {
    fun clamp(): PadConfig = copy(
        inputMode = inputMode.coerceIn(0, INPUT_MAX),
        socdMode = socdMode.coerceIn(0, SOCD_MAX),
        dpadMode = dpadMode.coerceIn(0, DPAD_MAX),
        fourWay = fourWay.coerceIn(0, 1),
        invertX = invertX.coerceIn(0, 1),
        invertY = invertY.coerceIn(0, 1),
        debounce = debounce.coerceIn(DEBOUNCE_MIN, DEBOUNCE_MAX),
    )

    fun toBytes(): ByteArray {
        val c = clamp()
        return byteArrayOf(
            c.inputMode.toByte(),
            c.socdMode.toByte(),
            c.dpadMode.toByte(),
            ((if (c.fourWay != 0) 1 else 0) or (if (c.invertX != 0) 2 else 0) or
                (if (c.invertY != 0) 4 else 0)).toByte(),
            c.debounce.toByte(),
        )
    }

    /** 这一改动会不会让 Pico 重启？界面据此提示"设备重启中"，别让用户以为掉线了。 */
    fun rebootsDeviceComparedTo(o: PadConfig): Boolean = clamp().inputMode != o.clamp().inputMode

    companion object {
        const val BYTES = 5
        const val INPUT_MAX = 16
        const val SOCD_MAX = 4
        const val DPAD_MAX = 2
        const val DEBOUNCE_MIN = 1
        const val DEBOUNCE_MAX = 20

        /** 和设备菜单同名同序（固件里的 INPUT_NAMES / SOCD_NAMES / DPAD_NAMES）。 */
        val INPUT_NAMES = listOf(
            "XIN", "SW", "PS3", "KBD", "PS4", "XB1", "MDM", "NEO", "PCE",
            "EGR", "AST", "PSC", "XBO", "PS5", "GEN", "SWP", "P5G",
        )
        val SOCD_NAMES = listOf("UP", "NEU", "2ND", "1ST", "BYP")
        val DPAD_NAMES = listOf("DIG", "LAN", "RAN")

        fun fromBytes(b: ByteArray): PadConfig? {
            if (b.size < BYTES) return null
            fun u(i: Int) = b[i].toInt() and 0xFF
            val f = u(3)
            return PadConfig(
                inputMode = u(0),
                socdMode = u(1),
                dpadMode = u(2),
                fourWay = f and 0x01,
                invertX = (f shr 1) and 0x01,
                invertY = (f shr 2) and 0x01,
                debounce = u(4),
            ).clamp()
        }
    }
}

/**
 * 灯光设置（7 字节）。同样对齐 `pad_cfg.h`。
 *
 * 三个速度是**菜单的百分比**（0..100，越大越快）。固件发给 Pico 时才换成周期时间，
 * 换算表在 [speedToCycle] / [cycleToSpeed]，和固件 `pad_cfg.h` 里的那两个函数一致
 * （两边各有测试向量盯着，改一边必有一套红）。
 */
data class LedConfig(
    val animation: Int = 0,
    val brightness: Int = 5,
    val staticColor: Int = 0,
    val turnOffSuspended: Int = 0,
    val chaseSpeed: Int = 92,
    val rainbowSpeed: Int = 96,
    val flowSpeed: Int = 96,
) {
    fun clamp(): LedConfig = copy(
        animation = animation.coerceIn(0, ANIM_MAX),
        brightness = brightness.coerceIn(0, BRIGHT_MAX),
        staticColor = staticColor.coerceIn(0, COLOR_MAX),
        turnOffSuspended = turnOffSuspended.coerceIn(0, 1),
        chaseSpeed = chaseSpeed.coerceIn(0, SPEED_MAX),
        rainbowSpeed = rainbowSpeed.coerceIn(0, SPEED_MAX),
        flowSpeed = flowSpeed.coerceIn(0, SPEED_MAX),
    )

    fun toBytes(): ByteArray {
        val c = clamp()
        return byteArrayOf(
            c.animation.toByte(),
            c.brightness.toByte(),
            c.staticColor.toByte(),
            (if (c.turnOffSuspended != 0) 1 else 0).toByte(),
            c.chaseSpeed.toByte(),
            c.rainbowSpeed.toByte(),
            c.flowSpeed.toByte(),
        )
    }

    fun sameAs(o: LedConfig): Boolean = clamp() == o.clamp()

    companion object {
        const val BYTES = 7
        const val ANIM_MAX = 5
        const val BRIGHT_MAX = 5
        const val COLOR_MAX = 15
        const val SPEED_MAX = 100

        /** 和设备菜单同名同序（固件里的 ANIM_NAMES / COLOR_NAMES）。 */
        val ANIM_NAMES = listOf("静态", "彩虹", "追逐", "主题", "自定义", "流水")
        val COLOR_NAMES = listOf(
            "BLK", "WHT", "RED", "ORG", "YEL", "LME", "GRN", "SEA",
            "AQU", "SKY", "BLU", "PUR", "PNK", "MAG", "IND", "VIO",
        )

        /** 速度(0..100) → Pico 的周期时间(1..1001)。和设备菜单原来的公式一致。 */
        fun speedToCycle(speed: Int): Int = (100 - speed.coerceIn(0, SPEED_MAX)) * 10 + 1

        /** 周期时间 → 速度。0（老配置）当速度上限，别显示成 101%。 */
        fun cycleToSpeed(cycle: Int): Int =
            if (cycle <= 0) SPEED_MAX else (100 - (cycle - 1) / 10).coerceIn(0, SPEED_MAX)

        fun fromBytes(b: ByteArray): LedConfig? {
            if (b.size < BYTES) return null
            fun u(i: Int) = b[i].toInt() and 0xFF
            return LedConfig(
                animation = u(0),
                brightness = u(1),
                staticColor = u(2),
                turnOffSuspended = u(3) and 0x01,
                chaseSpeed = u(4),
                rainbowSpeed = u(5),
                flowSpeed = u(6),
            ).clamp()
        }
    }
}
