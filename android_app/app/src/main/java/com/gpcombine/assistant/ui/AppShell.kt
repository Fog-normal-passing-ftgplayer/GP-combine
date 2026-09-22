package com.gpcombine.assistant.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.gpcombine.assistant.BuildConfig
import com.gpcombine.assistant.ble.ScannedDevice
import com.gpcombine.assistant.store.Prefs

/**
 * 底栏四格。诊断默认不出现，连点"关于"页的版本号 5 次才放出来。
 *
 * 用自己的底栏而不是 Material 的 NavigationBar：后者必须给图标，而这版不想为了
 * 四个图标去拉 material-icons 依赖（本地离线构建里没有）。
 */
private enum class Tab(val label: String) {
    HOME("首页"),
    CONFIG("配置"),
    TERM("终端"),
    DIAG("诊断"),
    ABOUT("关于"),
}

@Composable
fun AppShell(
    vm: DeviceViewModel,
    ui: UiState,
    onScan: () -> Unit,
    onConnect: (ScannedDevice) -> Unit,
    onCode: (String) -> Unit,
    onFake: () -> Unit,
) {
    val ctx = LocalContext.current
    val prefs = remember { Prefs(ctx) }
    var unlocked by remember { mutableStateOf(prefs.diagUnlocked) }
    var tab by remember { mutableStateOf(Tab.HOME) }
    var taps by remember { mutableIntStateOf(0) }
    val cfgState by vm.config.state.collectAsStateWithLifecycle()
    val termState by vm.terminal.state.collectAsStateWithLifecycle()

    val tabs = Tab.entries.filter { it != Tab.DIAG || unlocked }
    // 解锁后又点了"关于"：别停在一个已经不存在的 tab 上
    if (tab !in tabs) tab = Tab.HOME

    Scaffold(
        bottomBar = {
            BottomBar(tabs, tab) { next ->
                // 离开配置页时把 debounce 里的最后一次改动送出去
                if (tab == Tab.CONFIG && next != Tab.CONFIG) vm.configFlush()
                tab = next
            }
        },
    ) { pad ->
        Column(Modifier.fillMaxSize().padding(pad)) {
            when (tab) {
                Tab.HOME -> ConnectScreen(ui, onScan, onConnect, onCode, onFake)
                Tab.CONFIG -> ConfigScreen(
                    state = cfgState,
                    onEdit = vm::configEdit,
                    onSave = vm::configSave,
                    onReset = vm::configReset,
                    onRefresh = vm::configRefresh,
                )
                Tab.TERM -> TerminalScreen(
                    state = termState,
                    onSend = vm::terminalSend,
                    onClear = vm::terminalClear,
                    onTogglePush = vm::terminalShowPush,
                )
                Tab.DIAG -> DiagScreen(ui, vm)
                Tab.ABOUT -> AboutScreen(
                    ui = ui,
                    unlocked = unlocked,
                    onVersionTap = {
                        taps++
                        if (taps >= 5 && !unlocked) {
                            unlocked = true
                            prefs.diagUnlocked = true
                            tab = Tab.DIAG
                        }
                    },
                )
            }
        }
    }
}

@Composable
private fun BottomBar(tabs: List<Tab>, current: Tab, onSelect: (Tab) -> Unit) {
    Surface(tonalElevation = 3.dp) {
        Row(Modifier.fillMaxWidth().height(58.dp)) {
            tabs.forEach { t ->
                val selected = t == current
                val color = if (selected) MaterialTheme.colorScheme.primary
                else MaterialTheme.colorScheme.onSurfaceVariant
                Column(
                    modifier = Modifier.weight(1f).fillMaxHeight().clickable { onSelect(t) },
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center,
                ) {
                    Text(t.label, color = color, style = MaterialTheme.typography.titleSmall)
                    Box(
                        Modifier.padding(top = 4.dp).height(3.dp).fillMaxWidth(0.4f)
                            .background(
                                if (selected) MaterialTheme.colorScheme.primary else Color.Transparent
                            )
                    )
                }
            }
        }
    }
}

@Composable
private fun AboutScreen(ui: UiState, unlocked: Boolean, onVersionTap: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text("关于", style = MaterialTheme.typography.titleMedium)
        Card {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("GP-Combine 配置助手", style = MaterialTheme.typography.titleSmall)
                Row {
                    Text("当前版本：${BuildConfig.VERSION_NAME}（build ${BuildConfig.VERSION_CODE}）")
                }
                // 版本号这一行是诊断页的暗门：连点 5 次
                Text(
                    text = if (unlocked) "诊断已解锁（底栏多一格）" else "连点这一行 5 次可以打开诊断",
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.fillMaxWidth().padding(top = 4.dp).clickableText(onVersionTap),
                )
            }
        }
        Card {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("设备", style = MaterialTheme.typography.titleSmall)
                if (ui.phase == Phase.READY) {
                    Text("名称：${ui.pair?.name ?: ui.deviceName}")
                    Text("固件：${ui.info?.version ?: "未知"}")
                    Text("协议：A5 5A，CRC16-CCITT")
                } else {
                    Text("还没连上设备。先回首页扫描。")
                }
            }
        }
        Card {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("日志落盘", style = MaterialTheme.typography.titleSmall)
                Text(ui.logFile ?: "还没开日志文件", style = MaterialTheme.typography.bodySmall)
                Text("每次开 App 一个文件，只留最近 5 个会话。导出在诊断 → 日志页。")
            }
        }
    }
}

private fun Modifier.clickableText(onClick: () -> Unit): Modifier = this.clickable { onClick() }
