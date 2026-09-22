package com.gpcombine.assistant.ui

import java.io.File
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * 布局护栏：**同一方向不能套两层滚动**。
 *
 * `Modifier.verticalScroll` 的节点在测量第一步就会 `require(maxHeight != Infinity)`
 * （foundation 的 `checkScrollableContainerConstraints`）。它一旦被放进另一个
 * `verticalScroll`（或 LazyColumn）里，拿到的最大高度就是无穷大，测量当场抛
 * `IllegalArgumentException: Vertically scrollable component was measured with an
 * infinity maximum height constraints, ...` —— App 直接崩，且只在切到那一页时崩。
 *
 * 设置页的四个新页（手柄/灯光/蓝牙/配置档）就是这么崩的：`ConfigScreen` 已经在
 * 外面套了一层 `verticalScroll`，四个 Tab 各自又套了一层。
 */
class UiScrollGuardTest {
    private fun uiSource(name: String): String {
        val rel = "com/gpcombine/assistant/ui/$name"
        val candidates = listOf("src/main/java/$rel", "app/src/main/java/$rel")
        val f = candidates.map { File(it) }.firstOrNull { it.isFile }
            ?: error("找不到 $name，试过：$candidates（工作目录 ${File(".").absolutePath}）")
        return f.readText()
    }

    /** 去掉注释行，避免"注释里提到 verticalScroll"也算命中。 */
    private fun code(src: String): String =
        src.lines().filterNot { it.trimStart().startsWith("//") || it.trimStart().startsWith("*") }
            .joinToString("\n")

    @Test
    fun configScreenIsTheOneThatScrolls() {
        assertTrue(
            "ConfigScreen 必须自己带一层 verticalScroll：Tab 里的内容全靠它滚",
            code(uiSource("ConfigScreen.kt")).contains("verticalScroll("),
        )
    }

    @Test
    fun tabsDoNotScrollThemselves() {
        assertFalse(
            "DeviceTabs 里的页是 ConfigScreen 那层 verticalScroll 的子级，自己再套一层会在" +
                "测量时抛 infinity maximum height 约束异常（App 崩溃）",
            code(uiSource("DeviceTabs.kt")).contains("verticalScroll("),
        )
        assertFalse(
            "同上：LazyColumn / LazyRow 在已有滚动父级里会被测成无穷大高度，一样崩",
            Regex("(LazyColumn|LazyRow|horizontalScroll)\\(")
                .containsMatchIn(code(uiSource("DeviceTabs.kt"))),
        )
    }
}
