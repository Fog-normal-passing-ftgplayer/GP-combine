package com.gpcombine.assistant.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.gpcombine.assistant.config.BtState
import com.gpcombine.assistant.config.LedState
import com.gpcombine.assistant.config.PadState
import com.gpcombine.assistant.config.ProfileState
import com.gpcombine.assistant.proto.LedConfig
import com.gpcombine.assistant.proto.PadConfig
import com.gpcombine.assistant.proto.Profiles

/** 三个速度滑条共用：0..100，越大越快（和设备菜单同一个方向）。 */
@Composable
private fun SpeedRow(label: String, value: Int, onChange: (Int) -> Unit) {
    SliderRow(label, value, onChange)
}

// ---- 手柄 ----
@Composable
internal fun PadTab(
    state: PadState,
    onEdit: (PadConfig) -> Unit,
    onApply: () -> Unit,
    onRefresh: () -> Unit,
) {
    val cfg = state.cfg
    val restart = state.onDevice != null && cfg.rebootsDeviceComparedTo(state.onDevice)
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        Text(
            "手柄设置存在 Pico 上（不是 ESP32 的 17 项里）。改完点「应用到设备」才下发。",
            style = MaterialTheme.typography.bodySmall,
        )
        EnumRow("输入模式", PadConfig.INPUT_NAMES, cfg.inputMode) { onEdit(cfg.copy(inputMode = it)) }
        EnumRow("SOCD 模式", PadConfig.SOCD_NAMES, cfg.socdMode) { onEdit(cfg.copy(socdMode = it)) }
        EnumRow("D-Pad 模式", PadConfig.DPAD_NAMES, cfg.dpadMode) { onEdit(cfg.copy(dpadMode = it)) }
        SwitchRow("四向模式", cfg.fourWay == 1) { onEdit(cfg.copy(fourWay = if (it) 1 else 0)) }
        SwitchRow("反向 X", cfg.invertX == 1) { onEdit(cfg.copy(invertX = if (it) 1 else 0)) }
        SwitchRow("反向 Y", cfg.invertY == 1) { onEdit(cfg.copy(invertY = if (it) 1 else 0)) }
        StepperRow("去抖延迟", "${cfg.debounce} ms", step = 1, value = cfg.debounce,
            lo = PadConfig.DEBOUNCE_MIN, hi = PadConfig.DEBOUNCE_MAX) {
            onEdit(cfg.copy(debounce = it))
        }
        if (restart) {
            Text(
                "换了输入模式：下发后 Pico 会自己重启一下（1~2 秒），屏幕上会短暂黑一下。",
                color = MaterialTheme.colorScheme.primary,
                style = MaterialTheme.typography.bodySmall,
            )
        }
        Row(
            Modifier.fillMaxWidth().padding(top = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Button(onClick = onApply, enabled = !state.applying && state.dirty) {
                Text(if (state.applying) "下发中…" else "应用到设备")
            }
            OutlinedButton(onClick = onRefresh, enabled = !state.loading) { Text("重新读取") }
        }
        state.note?.let { Text(it, color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.bodySmall) }
        state.error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
        Text(
            "按键映射（哪个键对应哪个功能）不在 App 里改，走设备菜单。",
            style = MaterialTheme.typography.bodySmall,
        )
    }
}

// ---- 灯光 ----
@Composable
internal fun LedTab(
    state: LedState,
    onEdit: (LedConfig) -> Unit,
    onFlush: () -> Unit,
) {
    val cfg = state.cfg
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        Text(
            "灯光改了不会重启设备，调一下就能在灯上看见（300ms 内合并下发）。",
            style = MaterialTheme.typography.bodySmall,
        )
        EnumRow("动画模式", LedConfig.ANIM_NAMES, cfg.animation) { onEdit(cfg.copy(animation = it)) }
        StepperRow("亮度", "${cfg.brightness} / ${LedConfig.BRIGHT_MAX}", step = 1,
            value = cfg.brightness, lo = 0, hi = LedConfig.BRIGHT_MAX) {
            onEdit(cfg.copy(brightness = it))
        }
        EnumRow("静态颜色", LedConfig.COLOR_NAMES, cfg.staticColor) {
            onEdit(cfg.copy(staticColor = it))
        }
        SpeedRow("追逐速度", cfg.chaseSpeed) { onEdit(cfg.copy(chaseSpeed = it)) }
        SpeedRow("彩虹速度", cfg.rainbowSpeed) { onEdit(cfg.copy(rainbowSpeed = it)) }
        SpeedRow("流水速度", cfg.flowSpeed) { onEdit(cfg.copy(flowSpeed = it)) }
        SwitchRow("挂起关灯", cfg.turnOffSuspended == 1) {
            onEdit(cfg.copy(turnOffSuspended = if (it) 1 else 0))
        }
        Row(
            Modifier.fillMaxWidth().padding(top = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Button(onClick = onFlush) { Text("立即下发") }
        }
        state.error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
        Text("灯光和其它设置一样存在 Pico flash 里，断电重启仍然保持。",
            style = MaterialTheme.typography.bodySmall)
    }
}

// ---- 蓝牙 ----
@Composable
internal fun BluetoothTab(
    state: BtState,
    onSetName: (String) -> Unit,
    onSetPairCode: (String) -> Unit,
    onRegenerate: () -> Unit,
    onSetEnabled: (Boolean) -> Unit,
    onRefresh: () -> Unit,
) {
    var nameDialog by remember { mutableStateOf<String?>(null) }
    var pairDialog by remember { mutableStateOf<String?>(null) }
    var showPair by remember { mutableStateOf(false) }
    var confirmRegen by remember { mutableStateOf(false) }
    val info = state.info

    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Card {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("设备", style = MaterialTheme.typography.titleSmall)
                Text("名称：${info?.name ?: "（还没读到）"}")
                Text("配对码：${info?.pairCode ?: "—"}")
                Text(
                    "已连手机：${info?.clients ?: 0} 台　广播：" +
                        when (info?.link) {
                            2 -> "已连接"
                            1 -> "广播中"
                            else -> "未启动"
                        },
                )
                Text(
                    "开关：${if (info?.btEnabled == true) "开（nRF 已停）" else "关（nRF 可用）"}",
                )
            }
        }

        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text("蓝牙开关", modifier = Modifier.weight(1f))
            Switch(
                checked = info?.btEnabled == true,
                enabled = info != null && !state.busy,
                onCheckedChange = onSetEnabled,
            )
        }
        Text(
            "蓝牙和 nRF 手柄输出共用一个 2.4G 射频，固件里是互斥的：蓝牙开着，nRF 就停。",
            style = MaterialTheme.typography.bodySmall,
        )

        HorizontalDivider()
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(
                onClick = { nameDialog = info?.name ?: "" },
                enabled = info != null && !state.busy,
            ) { Text("改设备名") }
            OutlinedButton(
                onClick = { showPair = !showPair },
                enabled = info != null,
            ) { Text(if (showPair) "隐藏配对码" else "显示配对码") }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(
                onClick = { pairDialog = info?.pairCode ?: "" },
                enabled = info != null && !state.busy,
            ) { Text("自定义配对码") }
            OutlinedButton(onClick = { confirmRegen = true }, enabled = !state.busy) {
                Text("随机换码")
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = onRefresh, enabled = !state.loading) { Text("重新读取") }
        }

        if (showPair) {
            Text("当前配对码：${info?.pairCode ?: "—"}　（手机 App 连的就是它）")
        }
        Text(
            "改名字：只重启广播，正在连的手机不断。\n" +
                "换配对码：设备会作废当前会话并断开所有手机 —— 换码不踢人等于没换。" +
                "App 会把新码存下来，自己用新码连回来。",
            style = MaterialTheme.typography.bodySmall,
        )
        state.note?.let { Text(it, color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.bodySmall) }
        state.sessionReset?.let {
            Text("会话已被设备作废，App 正在用新配对码重连…",
                color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.bodySmall)
        }
        state.error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
    }

    nameDialog?.let { initial ->
        var text by remember(initial) { mutableStateOf(initial) }
        AlertDialog(
            onDismissRequest = { nameDialog = null },
            title = { Text("改设备名") },
            text = {
                Column {
                    OutlinedTextField(
                        value = text,
                        onValueChange = { text = it },
                        label = { Text("广播名（最多 20 字节，中文一个字 3 字节）") },
                    )
                    Text("手机蓝牙列表里看到的就是这个名字。", style = MaterialTheme.typography.bodySmall)
                }
            },
            confirmButton = {
                TextButton(onClick = { nameDialog = null; onSetName(text) }) { Text("改") }
            },
            dismissButton = { TextButton(onClick = { nameDialog = null }) { Text("取消") } },
        )
    }

    pairDialog?.let { initial ->
        var text by remember(initial) { mutableStateOf(initial) }
        AlertDialog(
            onDismissRequest = { pairDialog = null },
            title = { Text("自定义配对码") },
            text = {
                Column {
                    OutlinedTextField(
                        value = text,
                        onValueChange = { v -> text = v.filter { it in '0'..'9' }.take(6) },
                        label = { Text("6 位数字") },
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                        visualTransformation = PasswordVisualTransformation(),
                    )
                    Text("改完设备会断开所有手机，App 用这个新码自己连回来。",
                        style = MaterialTheme.typography.bodySmall)
                }
            },
            confirmButton = {
                TextButton(
                    onClick = { pairDialog = null; onSetPairCode(text) },
                    enabled = text.length == 6,
                ) { Text("换码") }
            },
            dismissButton = { TextButton(onClick = { pairDialog = null }) { Text("取消") } },
        )
    }

    if (confirmRegen) {
        AlertDialog(
            onDismissRequest = { confirmRegen = false },
            title = { Text("随机换一个配对码？") },
            text = { Text("设备会自己生成 6 位新码，并立刻断开所有已连手机（包括这台）。App 拿到新码后会自己连回来。") },
            confirmButton = {
                TextButton(onClick = { confirmRegen = false; onRegenerate() }) { Text("换码") }
            },
            dismissButton = { TextButton(onClick = { confirmRegen = false }) { Text("取消") } },
        )
    }
}

// ---- 配置档 ----
@Composable
internal fun ProfileTab(
    state: ProfileState,
    onSave: (Int, String) -> Unit,
    onLoad: (Int) -> Unit,
    onRename: (Int, String) -> Unit,
    onDelete: (Int) -> Unit,
    onRefresh: () -> Unit,
) {
    var saveSlot by remember { mutableStateOf<Int?>(null) }
    var renameSlot by remember { mutableStateOf<Int?>(null) }
    var deleteSlot by remember { mutableStateOf<Int?>(null) }

    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text("配置档存在设备里（/profiles/1..5.cfg）。", style = MaterialTheme.typography.bodySmall)
        Text(
            "「存为档」存的是**设备此刻的设置**，不是 App 手里那份；加载档会让设备当场变成那份设置。",
            style = MaterialTheme.typography.bodySmall,
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = onRefresh, enabled = !state.loading) { Text("重新读取") }
        }
        state.slots.forEach { e ->
            Card {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("档${e.slot}", style = MaterialTheme.typography.titleSmall,
                            modifier = Modifier.padding(end = 8.dp))
                        Text(
                            if (e.used) Profiles.displayName(e) else "（空）",
                            modifier = Modifier.weight(1f),
                        )
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(onClick = { saveSlot = e.slot }, enabled = !state.busy) {
                            Text("存为档")
                        }
                        OutlinedButton(
                            onClick = { onLoad(e.slot) },
                            enabled = e.used && !state.busy,
                        ) { Text("加载") }
                        OutlinedButton(
                            onClick = { renameSlot = e.slot },
                            enabled = e.used && !state.busy,
                        ) { Text("改名") }
                        OutlinedButton(
                            onClick = { deleteSlot = e.slot },
                            enabled = e.used && !state.busy,
                        ) { Text("删除") }
                    }
                }
            }
        }
        state.note?.let { Text(it, color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.bodySmall) }
        state.error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
    }

    saveSlot?.let { slot ->
        var text by remember(slot) { mutableStateOf("") }
        AlertDialog(
            onDismissRequest = { saveSlot = null },
            title = { Text("存进档$slot") },
            text = {
                Column {
                    OutlinedTextField(
                        value = text,
                        onValueChange = { text = it },
                        label = { Text("档名（可留空，留空显示成「档$slot」）") },
                    )
                    Text("存的是设备此刻的设置，会覆盖档$slot 里原来的内容。",
                        style = MaterialTheme.typography.bodySmall)
                }
            },
            confirmButton = {
                TextButton(onClick = { saveSlot = null; onSave(slot, text) }) { Text("存") }
            },
            dismissButton = { TextButton(onClick = { saveSlot = null }) { Text("取消") } },
        )
    }

    renameSlot?.let { slot ->
        val cur = state.slots.firstOrNull { it.slot == slot }?.name ?: ""
        var text by remember(slot) { mutableStateOf(cur) }
        AlertDialog(
            onDismissRequest = { renameSlot = null },
            title = { Text("档$slot 改名") },
            text = {
                Column {
                    OutlinedTextField(
                        value = text,
                        onValueChange = { text = it },
                        label = { Text("新档名") },
                    )
                    Text("只改名字，档里存着的那份设置不动。", style = MaterialTheme.typography.bodySmall)
                }
            },
            confirmButton = {
                TextButton(onClick = { renameSlot = null; onRename(slot, text) }) { Text("改名") }
            },
            dismissButton = { TextButton(onClick = { renameSlot = null }) { Text("取消") } },
        )
    }

    deleteSlot?.let { slot ->
        AlertDialog(
            onDismissRequest = { deleteSlot = null },
            title = { Text("删除档$slot？") },
            text = { Text("只删这一档，设备当前的设置不受影响。删了就找不回来了。") },
            confirmButton = {
                TextButton(onClick = { deleteSlot = null; onDelete(slot) }) { Text("删除") }
            },
            dismissButton = { TextButton(onClick = { deleteSlot = null }) { Text("取消") } },
        )
    }
}
