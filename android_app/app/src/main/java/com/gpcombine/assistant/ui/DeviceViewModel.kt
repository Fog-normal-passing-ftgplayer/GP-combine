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
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

enum class Phase { IDLE, SCANNING, NEED_CODE, WORKING, READY }

data class UiState(
    val phase: Phase = Phase.IDLE,
    val devices: List<ScannedDevice> = emptyList(),
    val deviceName: String = "",
    val info: DeviceInfo? = null,
    val pair: PairInfo? = null,
    val error: String? = null,
)

class DeviceViewModel(app: Application, private val useFake: Boolean) : AndroidViewModel(app) {
    private val transport: BleTransport =
        if (useFake) FakeTransport() else AndroidBleTransport(app)
    private val client = DeviceClient(transport, viewModelScope, timeoutMs = 4000)
    private val prefs = Prefs(app)

    private val _ui = MutableStateFlow(UiState())
    val ui: StateFlow<UiState> = _ui.asStateFlow()

    private var scanJob: Job? = null

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
                transport.state.collect { st ->
                    if (st == BleState.CONNECTED) {
                        _ui.update { it.copy(phase = Phase.NEED_CODE) }
                    }
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
