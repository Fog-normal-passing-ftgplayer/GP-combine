package com.gpcombine.assistant.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val Colors = darkColorScheme(
    primary = Color(0xFF6FD3FF),
    onPrimary = Color(0xFF00344A),
    surface = Color(0xFF1B1B1F),
    background = Color(0xFF111114),
)

@Composable
fun GPCombineTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = Colors, content = content)
}
