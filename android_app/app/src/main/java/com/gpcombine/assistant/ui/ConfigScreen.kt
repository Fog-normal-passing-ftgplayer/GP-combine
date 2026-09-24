package com.gpcombine.assistant.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.gpcombine.assistant.config.ConfigState
import com.gpcombine.assistant.proto.EspConfig
import kotlin.math.roundToInt

/**
 * 设置页。分四组（显示 / 输入 / 休眠 / 无线），对应设备菜单里那几页。
 *
 * 语义和设备菜单一致：改一下立刻下发（`CFG_APPLY`，不写 flash，设备屏幕当场变），
 * 点「保存到设备」才落盘（`CFG_SET`）。所以顶部一直显示"有未保存的改动"。
 */
@Composable
fun ConfigScreen(
    state: ConfigState,
    onEdit: (EspConfig) -> Unit,
    onSave: () -> Unit,
    onReset: () -> Unit,
    onRefresh: () -> Unit,
) {
    var inner by remember { mutableIntStateOf(0) }
    var confirmReset by remember { mutableStateOf(false) }
    val titles = listOf("显示", "输入", "休眠", "无线")
    val cfg = state.cfg

    Column(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp)) {
            Text("设备设置", style = MaterialTheme.typography.titleMedium)
            state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            when {
                state.loading -> Text("正在读设备设置…", style = MaterialTheme.typography.bodySmall)
                state.onDevice == null -> Text(
                    "还没读到设备设置（改动会照发，但「已保存」这个判断暂时不可靠）",
                    style = MaterialTheme.typography.bodySmall,
                )
                state.dirty -> Text(
                    "有未保存的改动：设备已经按新值在显示，但断电重启会回到旧值",
                    color = MaterialTheme.colorScheme.primary,
                    style = MaterialTheme.typography.bodySmall,
                )
                state.justSaved -> Text("已写入设备", style = MaterialTheme.typography.bodySmall)
                else -> Text("和设备一致", style = MaterialTheme.typography.bodySmall)
            }
            Row(
                Modifier.fillMaxWidth().padding(top = 6.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Button(onClick = onSave, enabled = !state.saving) {
                    Text(if (state.saving) "写入中…" else "保存到设备")
                }
                OutlinedButton(onClick = onRefresh, enabled = !state.loading) { Text("重新读取") }
                OutlinedButton(onClick = { confirmReset = true }, enabled = !state.saving) {
                    Text("恢复默认")
                }
            }
        }

        TabRow(selectedTabIndex = inner) {
            titles.forEachIndexed { i, t ->
                Tab(selected = inner == i, onClick = { inner = i }, text = { Text(t) })
            }
        }

        Column(
            modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp),
        ) {
            when (inner) {
                0 -> {
                    EnumRow("主题", EspConfig.THEME_NAMES, cfg.theme) { onEdit(cfg.copy(theme = it)) }
                    EnumRow("风格", EspConfig.STYLE_NAMES, cfg.style) { onEdit(cfg.copy(style = it)) }
                    EnumRow("背景透明度", EspConfig.OPACITY_NAMES, cfg.bgOpacity) {
                        onEdit(cfg.copy(bgOpacity = it))
                    }
                    SliderRow("背光亮度", cfg.backlight) { onEdit(cfg.copy(backlight = it)) }
                    SwitchRow("水平翻转", cfg.flipX == 1) { onEdit(cfg.copy(flipX = if (it) 1 else 0)) }
                    SwitchRow("垂直翻转", cfg.flipY == 1) { onEdit(cfg.copy(flipY = if (it) 1 else 0)) }
                    SwitchRow("反色", cfg.invert == 1) { onEdit(cfg.copy(invert = if (it) 1 else 0)) }
                }
                1 -> {
                    SwitchRow("输入历史", cfg.inputHistory == 1) {
                        onEdit(cfg.copy(inputHistory = if (it) 1 else 0))
                    }
                    EnumRow("按键布局", EspConfig.LAYOUT_NAMES, cfg.layout) {
                        onEdit(cfg.copy(layout = it))
                    }
                    Text(
                        "按键映射（哪个键对应哪个功能）不在 App 里改，走设备菜单。",
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
                2 -> {
                    EnumRow("屏保模式", EspConfig.SAVER_NAMES, cfg.saverMode) {
                        onEdit(cfg.copy(saverMode = it))
                    }
                    StepperRow("屏保时间", "${cfg.saverSecs} 秒", step = 10, value = cfg.saverSecs,
                        lo = 0, hi = EspConfig.SAVER_SECS_MAX) { onEdit(cfg.copy(saverSecs = it)) }
                    SwitchRow("关屏", cfg.screenOff == 1) {
                        onEdit(cfg.copy(screenOff = if (it) 1 else 0))
                    }
                    Text(
                        "屏保模式和屏保时间以设备为准：动态壁纸开着时屏保会被固件强制关掉。",
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
                else -> {
                    SwitchRow("nRF 无线", cfg.wireless == 1) {
                        onEdit(cfg.copy(wireless = if (it) 1 else 0))
                    }
                    Card {
                        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text("互斥关系", style = MaterialTheme.typography.titleSmall)
                            Text("蓝牙开着时 nRF 会停：两者共用一个 2.4G 射频，固件里就是这么干的。")
                            Text("蓝牙开关 / 设备名 / 配对码在设备菜单的「蓝牙」页改（App 改这些要单独的命令，排在下一批）。")
                        }
                    }
                }
            }
        }
    }

    if (confirmReset) {
        AlertDialog(
            onDismissRequest = { confirmReset = false },
            title = { Text("恢复默认？") },
            text = { Text("设备上所有设置项会回到出厂值并立即写入 flash（主题、背光、屏保、输入历史、无线开关都会变）。这个不好撤销。") },
            confirmButton = {
                TextButton(onClick = { confirmReset = false; onReset() }) { Text("恢复默认") }
            },
            dismissButton = { TextButton(onClick = { confirmReset = false }) { Text("取消") } },
        )
    }
}

/** 枚举项：◀ 值 ▶，和设备菜单的左右切换一致。 */
@Composable
private fun EnumRow(label: String, names: List<String>, value: Int, onChange: (Int) -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, modifier = Modifier.weight(1f))
        OutlinedButton(onClick = { onChange((value - 1 + names.size) % names.size) }) { Text("◀") }
        Text(
            text = names.getOrElse(value) { "?" },
            modifier = Modifier.widthIn(min = 76.dp).padding(horizontal = 6.dp),
            textAlign = TextAlign.Center,
        )
        OutlinedButton(onClick = { onChange((value + 1) % names.size) }) { Text("▶") }
    }
}

@Composable
private fun StepperRow(
    label: String,
    shown: String,
    step: Int,
    value: Int,
    lo: Int,
    hi: Int,
    onChange: (Int) -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, modifier = Modifier.weight(1f))
        OutlinedButton(onClick = { onChange((value - step).coerceIn(lo, hi)) }) { Text("−") }
        Text(shown, modifier = Modifier.widthIn(min = 76.dp).padding(horizontal = 6.dp),
            textAlign = TextAlign.Center)
        OutlinedButton(onClick = { onChange((value + step).coerceIn(lo, hi)) }) { Text("+") }
    }
}

@Composable
private fun SliderRow(label: String, value: Int, onChange: (Int) -> Unit) {
    Column(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Text("$label：$value")
        Slider(
            value = value.toFloat(),
            onValueChange = { onChange(it.roundToInt().coerceIn(0, 100)) },
            valueRange = 0f..100f,
        )
    }
}

@Composable
private fun SwitchRow(label: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, modifier = Modifier.weight(1f))
        Switch(checked = checked, onCheckedChange = onChange)
    }
}
