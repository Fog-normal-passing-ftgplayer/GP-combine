package com.gpcombine.assistant.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.gpcombine.assistant.ble.AndroidBleTransport
import com.gpcombine.assistant.ble.BleState
import com.gpcombine.assistant.ble.BleTransport
import com.gpcombine.assistant.ble.FakeTransport
import com.gpcombine.assistant.ble.ScannedDevice
import com.gpcombine.assistant.net.DeviceClient
import com.gpcombine.assistant.proto.DeviceInfo
import com.gpcombine.assistant.proto.PairInfo
import com.gpcombine.assistant.store.Prefs
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull

enum class Phase { IDLE, SCANNING, NEED_CODE, WORKING, READY }

data class UiState(
    val phase: Phase = Phase.IDLE,
    val devices: List<ScannedDevice> = emptyList(),
    val deviceName: String = "",
    val info: DeviceInfo? = null,
    val pair: PairInfo? = null,
    val error: String? = null,
    /** 蓝牙栈回调流水账，卡住的时候靠它定位是卡在哪一步。 */
    val trace: List<String> = emptyList(),
)

class DeviceViewModel(app: Application, private val useFake: Boolean) : AndroidViewModel(app) {
    private val transport: BleTransport =
        if (useFake) FakeTransport() else AndroidBleTransport(app)
    private val client = DeviceClient(transport, viewModelScope, timeoutMs = 4000)
    private val prefs = Prefs(app)

    private val _ui = MutableStateFlow(UiState())
    val ui: StateFlow<UiState> = _ui.asStateFlow()

    private var scanJob: Job? = null

    init {
        viewModelScope.launch {
            transport.log.collect { line ->
                _ui.update { it.copy(trace = (it.trace + line).takeLast(14)) }
            }
        }
    }

    fun startScan() {
        scanJob?.cancel()
        _ui.update { it.copy(phase = Phase.SCANNING, devices = emptyList(), error = null) }

        val fake = transport as? FakeTransport
        if (fake != null) {
            fake.connect()
            _ui.update { it.copy(phase = Phase.NEED_CODE, deviceName = "GP-Combine-FAKE（配对码 280148）") }
            // 存过配对码就直接过认证，省得每次手输
            prefs.pairCode?.let { submitCode(it) }
            return
        }

        val real = transport as AndroidBleTransport
        scanJob = viewModelScope.launch {
            runCatching {
                real.scan().collect { d ->
                    _ui.update { s -> s.copy(devices = (s.devices + d).distinctBy { it.address }) }
                }
            }.onFailure { e ->
                _ui.update { it.copy(phase = Phase.IDLE, error = e.message) }
            }
        }
    }

    fun connect(device: ScannedDevice) {
        scanJob?.cancel()
        scanJob = null
        _ui.update {
            it.copy(phase = Phase.WORKING, deviceName = device.name, error = null, devices = emptyList())
        }
        viewModelScope.launch {
            try {
                (transport as AndroidBleTransport).connect(device.address)
                prefs.lastAddress = device.address
                // 连接是异步完成的：等状态变 CONNECTED 再问配对码
                // 以前这里是无限等，蓝牙栈不回调就永远停在"通信中"，一点线索都没有
                val ok = withTimeoutOrNull(12_000) {
                    transport.state.first { it == BleState.CONNECTED }
                }
                if (ok == null) {
                    _ui.update {
                        it.copy(phase = Phase.IDLE, error = "12 秒没连上，卡在上面那一步")
                    }
                } else {
                    _ui.update { it.copy(phase = Phase.NEED_CODE) }
                }
            } catch (e: Exception) {
                _ui.update { it.copy(phase = Phase.IDLE, error = e.message) }
            }
        }
    }

    fun submitCode(code: String) {
        viewModelScope.launch {
            _ui.update { it.copy(phase = Phase.WORKING, error = null) }
            try {
                if (!client.auth(code)) {
                    _ui.update { it.copy(phase = Phase.NEED_CODE, error = "配对码不对，看设备屏幕") }
                    return@launch
                }
                prefs.pairCode = code
                loadDeviceInfo()
            } catch (e: Exception) {
                _ui.update { it.copy(phase = Phase.NEED_CODE, error = e.message) }
            }
        }
    }

    fun refresh() {
        viewModelScope.launch {
            _ui.update { it.copy(error = null) }
            try {
                loadDeviceInfo()
            } catch (e: Exception) {
                _ui.update { it.copy(error = e.message) }
            }
        }
    }

    private suspend fun loadDeviceInfo() {
        val info = client.info()
        val pair = client.pairInfo()
        _ui.update { it.copy(phase = Phase.READY, info = info, pair = pair, error = null) }
    }

    override fun onCleared() {
        client.close()
        (transport as? AndroidBleTransport)?.close()
    }

    companion object {
        fun factory(app: Application, useFake: Boolean) = viewModelFactory {
            initializer { DeviceViewModel(app, useFake) }
        }
    }
}
