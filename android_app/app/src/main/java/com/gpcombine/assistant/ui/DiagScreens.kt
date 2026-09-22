package com.gpcombine.assistant.ui

import android.content.Intent
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import com.gpcombine.assistant.diag.LogFormat
import com.gpcombine.assistant.diag.LogView
import com.gpcombine.assistant.net.Dir
import com.gpcombine.assistant.net.FrameRecord
import java.time.Instant
import java.time.ZoneId

/** 诊断三件套。入口藏在"关于"页（连点版本号 5 次）。 */
@Composable
fun DiagScreen(ui: UiState, vm: DeviceViewModel) {
    var inner by remember { mutableIntStateOf(0) }
    val titles = listOf("体检", "日志", "帧监视器")

    Column(Modifier.fillMaxSize()) {
        TabRow(selectedTabIndex = inner) {
            titles.forEachIndexed { i, t ->
                Tab(selected = inner == i, onClick = { inner = i }, text = { Text(t) })
            }
        }
        when (inner) {
            0 -> HealthScreen(ui, onRun = vm::runHealthCheck, onPolling = vm::setMemPolling)
            1 -> LogScreen(
                ui = ui,
                onPause = vm::setLogPaused,
                onClear = vm::clearLogs,
                onExport = { vm.logFile() },
            )
            else -> FrameScreen(ui)
        }
    }
}

// ---------------- 体检 ----------------

@Composable
fun HealthScreen(ui: UiState, onRun: () -> Unit, onPolling: (Boolean) -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Text("一键体检", style = MaterialTheme.typography.titleMedium)
        Text("PING 连发 20 轮看丢包和延迟，再读一次 INFO 看回包大小与内存。")
        Button(onClick = onRun, enabled = !ui.healthRunning) {
            Text(if (ui.healthRunning) "体检中…" else "开始体检")
        }
        ui.healthError?.let { Text("体检失败：$it", color = MaterialTheme.colorScheme.error) }

        ui.health?.let { r ->
            Card {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("PING ${r.ok}/${r.rounds} 通，丢 ${r.lost}", style = MaterialTheme.typography.titleSmall)
                    Text("延迟：最小 ${r.minMs} ms / 平均 ${r.avgMs} ms / 最大 ${r.maxMs} ms")
                    Text("协商 MTU：${r.mtu}" + if (r.mtu <= 23) "（= 默认值，没协商上，一帧会被切很多片）" else "")
                    Text("INFO 回包 ${r.infoBytes} 字节，按当前 MTU 估 ${r.infoChunks} 片（估算，不是实测分片数）")
                    r.info?.let {
                        Text("固件 ${it.version}，卡 ${mb(it.fsUsed)} / ${mb(it.fsTotal)}")
                        Text("内部 RAM 余 ${kb(it.ramFree)}，PSRAM 余 ${mb(it.psramFree)}")
                    }
                }
            }
        }

        Card {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("内存轮询", style = MaterialTheme.typography.titleSmall)
                        Text("每 2 秒读一次 INFO，画最近 2 分钟", style = MaterialTheme.typography.bodySmall)
                    }
                    Switch(checked = ui.memPolling, onCheckedChange = onPolling)
                }
                val last = ui.mem.lastOrNull()
                if (last == null) {
                    Text("还没采样。开了轮询才会画。", style = MaterialTheme.typography.bodySmall)
                } else {
                    Text("内部 RAM 余 ${kb(last.ramFree)}　PSRAM 余 ${mb(last.psramFree)}")
                    Text("采样 ${ui.mem.size} 点（${hhmmss(ui.mem.first().tsMs)} → ${hhmmss(last.tsMs)}）",
                        style = MaterialTheme.typography.bodySmall)
                    Sparkline(ui.mem.map { it.ramFree }, MaterialTheme.colorScheme.primary,
                        Modifier.fillMaxWidth().height(40.dp))
                    Sparkline(ui.mem.map { it.psramFree }, MaterialTheme.colorScheme.tertiary,
                        Modifier.fillMaxWidth().height(40.dp))
                    Text("上：内部 RAM（蓝）　下：PSRAM（绿）", style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}

/** 只画折线，不画坐标轴——目的是看"有没有一路往下掉"。 */
@Composable
private fun Sparkline(values: List<Long>, color: Color, modifier: Modifier) {
    Canvas(modifier) {
        if (values.size < 2) return@Canvas
        val mn = values.min()
        val span = (values.max() - mn).coerceAtLeast(1L).toFloat()
        val dx = size.width / (values.size - 1)
        var prev = Offset(0f, size.height - (values[0] - mn) / span * size.height)
        for (i in 1 until values.size) {
            val p = Offset(i * dx, size.height - (values[i] - mn) / span * size.height)
            drawLine(color, prev, p, strokeWidth = 3f)
            prev = p
        }
    }
}

// ---------------- 日志 ----------------

@Composable
fun LogScreen(ui: UiState, onPause: (Boolean) -> Unit, onClear: () -> Unit, onExport: () -> java.io.File?) {
    var filter by remember { mutableStateOf("") }
    val ctx = LocalContext.current
    val visible = LogView.visible(ui.logs, ui.logPausedAt, filter)
    val pending = LogView.pending(ui.logs, ui.logPausedAt)
    val listState = rememberLazyListState()

    // 跟随最新：只有没暂停的时候才滚，不然看得正好的那一屏会被顶走
    LaunchedEffect(visible.size, ui.logPausedAt) {
        if (ui.logPausedAt == null && visible.isNotEmpty()) {
            listState.scrollToItem(visible.size - 1)
        }
    }

    Column(Modifier.fillMaxSize().padding(12.dp)) {
        OutlinedTextField(
            value = filter,
            onValueChange = { filter = it },
            label = { Text("关键字过滤") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        Row(
            modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Button(onClick = { onPause(ui.logPausedAt == null) }) {
                Text(if (ui.logPausedAt == null) "暂停" else "继续")
            }
            OutlinedButton(onClick = onClear) { Text("清屏") }
            OutlinedButton(
                onClick = {
                    val f = onExport() ?: return@OutlinedButton
                    if (!f.exists()) return@OutlinedButton
                    val uri = FileProvider.getUriForFile(ctx, "${ctx.packageName}.files", f)
                    val send = Intent(Intent.ACTION_SEND).apply {
                        type = "text/plain"
                        putExtra(Intent.EXTRA_STREAM, uri)
                        putExtra(Intent.EXTRA_SUBJECT, f.name)
                        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    }
                    ctx.startActivity(Intent.createChooser(send, "导出日志"))
                },
                enabled = onExport()?.exists() == true,
            ) { Text("导出") }
        }
        Text(
            "共 ${ui.logs.size} 行，显示 ${visible.size} 行" +
                if (pending > 0) "；已暂停，攒了 $pending 行" else "",
            style = MaterialTheme.typography.bodySmall,
        )
        ui.logFile?.let { Text("落盘：$it", style = MaterialTheme.typography.bodySmall) }
        if (ui.phase != Phase.READY) {
            Text("还没连上设备：日志从连上并认证通过后才开始进来。", color = MaterialTheme.colorScheme.error)
        }

        LazyColumn(state = listState, modifier = Modifier.fillMaxSize().padding(top = 6.dp)) {
            items(visible) { l ->
                Text(
                    text = "${LogFormat.stamp(l.tsMs).substring(11)} [${LogFormat.tag(l.level)}] ${l.text}",
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.fillMaxWidth().padding(vertical = 1.dp),
                )
            }
        }
    }
}

// ---------------- 帧监视器 ----------------

@Composable
fun FrameScreen(ui: UiState) {
    var expanded by remember { mutableStateOf<Int?>(null) }

    Column(Modifier.fillMaxSize().padding(12.dp)) {
        Text("帧监视器", style = MaterialTheme.typography.titleMedium)
        Text("收发都记一条；\"无请求匹配\"是迟到或重放的回包（以前是直接丢掉的）。",
            style = MaterialTheme.typography.bodySmall)
        Text("共 ${ui.frames.size} 帧（最多留 ${DeviceViewModel.MAX_FRAMES} 条）",
            style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(bottom = 6.dp))

        val rows = ui.frames.asReversed()
        LazyColumn(Modifier.fillMaxSize()) {
            items(rows.size) { i ->
                val r = rows[i]
                val isOpen = expanded == i
                Card(
                    modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp)
                        .clickable { expanded = if (isOpen) null else i },
                ) {
                    Column(Modifier.padding(8.dp)) {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text(
                                text = if (r.dir == Dir.TX) "→ 发" else "← 收",
                                color = if (r.dir == Dir.TX) MaterialTheme.colorScheme.primary
                                else MaterialTheme.colorScheme.tertiary,
                                style = MaterialTheme.typography.bodySmall,
                            )
                            Text(hhmmss(r.timeMs), style = MaterialTheme.typography.bodySmall)
                            Text(FrameRecord.cmdName(r.cmd), style = MaterialTheme.typography.bodySmall)
                            Text("seq=${r.seq}", style = MaterialTheme.typography.bodySmall)
                            Text("${r.len}B", style = MaterialTheme.typography.bodySmall)
                        }
                        Text(r.hex.ifEmpty { "(无载荷)" }, style = MaterialTheme.typography.bodySmall)
                        if (isOpen) {
                            if (r.note.isNotEmpty()) Text("说明：${r.note}")
                            Text("cmd=0x%02X  seq=%d  载荷 %d 字节".format(r.cmd, r.seq, r.len))
                            if (r.text.isNotEmpty()) Text("按文本读：${r.text.take(120)}")
                        }
                    }
                }
            }
        }
    }
}

// ---------------- 小工具 ----------------

private fun hhmmss(ms: Long): String =
    Instant.ofEpochMilli(ms).atZone(ZoneId.systemDefault()).toLocalTime().toString()

private fun mb(v: Long) = "%.1f MB".format(v / 1048576.0)
private fun kb(v: Long) = "%.1f KB".format(v / 1024.0)
