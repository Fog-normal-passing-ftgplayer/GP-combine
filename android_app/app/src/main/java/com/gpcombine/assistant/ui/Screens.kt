package com.gpcombine.assistant.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.gpcombine.assistant.ble.ScannedDevice

@Composable
fun PermissionScreen(onRequest: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        Text("需要蓝牙权限", style = MaterialTheme.typography.titleLarge)
        Text("用来扫描并连接手柄上的蓝牙模块。Android 12 以下还需要定位权限，那是系统扫描蓝牙的硬性要求。")
        Button(onClick = onRequest, modifier = Modifier.padding(top = 16.dp)) { Text("去授权") }
    }
}

@Composable
fun ConnectScreen(
    ui: UiState,
    onScan: () -> Unit,
    onConnect: (ScannedDevice) -> Unit,
    onCode: (String) -> Unit,
    onFake: () -> Unit,
) {
    var code by remember { mutableStateOf("") }

    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        Text("GP-Combine", style = MaterialTheme.typography.headlineSmall)
        ui.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }

        when (ui.phase) {
            Phase.SCANNING -> {
                Text("正在扫描…")
                LazyColumn(modifier = Modifier.fillMaxWidth().padding(top = 8.dp)) {
                    items(ui.devices) { d ->
                        Card(
                            modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)
                                .clickable { onConnect(d) },
                        ) { Text("${d.name}   ${d.rssi} dBm", Modifier.padding(12.dp)) }
                    }
                }
            }

            Phase.NEED_CODE -> {
                Text("设备：${ui.deviceName}")
                Text("输入设备屏幕上显示的 6 位配对码")
                OutlinedTextField(
                    value = code,
                    onValueChange = { if (it.length <= 6) code = it.filter(Char::isDigit) },
                    label = { Text("配对码") },
                    modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
                )
                Button(onClick = { onCode(code) }, enabled = code.length == 6) { Text("连接") }
            }

            Phase.WORKING -> Text("通信中…")

            Phase.READY -> DeviceInfoSection(ui)

            Phase.IDLE -> Button(onClick = onScan, modifier = Modifier.padding(top = 16.dp)) {
                Text("扫描设备")
            }
        }

        // 没有板子时也能把整条状态机走通（假设备照抄固件的回包行为）
        if (ui.phase == Phase.IDLE) {
            Button(onClick = onFake, modifier = Modifier.padding(top = 8.dp)) {
                Text("假设备模式")
            }
        }
    }
}

/** 设备页：把 INFO / PAIR_INFO 的字段摊开显示。Task 7 接口里写的 DeviceScreen 就是这个。 */
@Composable
fun DeviceInfoSection(ui: UiState) {
    val info = ui.info
    val pair = ui.pair
    Column(modifier = Modifier.fillMaxWidth().padding(top = 8.dp)) {
        Text("设备：${pair?.name ?: ui.deviceName}", style = MaterialTheme.typography.titleMedium)
        info?.let {
            Text("固件版本：${it.version}")
            Text("固件大小：${mb(it.appBytes)}")
            Text("卡空间：已用 ${mb(it.fsUsed)} / 共 ${mb(it.fsTotal)}")
            Text("内部 RAM 余：${kb(it.ramFree)}")
            Text("PSRAM 余：${mb(it.psramFree)}")
        }
        pair?.let {
            Text("配对码：${it.pairCode}")
            Text("蓝牙：${if (it.btEnabled) "开" else "关"}    已连手机：${it.clients}")
        }
    }
}

private fun mb(v: Long) = "%.1f MB".format(v / 1048576.0)
private fun kb(v: Long) = "%.1f KB".format(v / 1024.0)
