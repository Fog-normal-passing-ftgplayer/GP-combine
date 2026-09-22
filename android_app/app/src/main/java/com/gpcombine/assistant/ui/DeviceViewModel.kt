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
import com.gpcombine.assistant.config.ConfigController
import com.gpcombine.assistant.config.BluetoothController
import com.gpcombine.assistant.config.LedController
import com.gpcombine.assistant.config.PadController
import com.gpcombine.assistant.config.ProfileController
import com.gpcombine.assistant.diag.LogFormat
import com.gpcombine.assistant.diag.LogLine
import com.gpcombine.assistant.diag.LogStore
import com.gpcombine.assistant.net.DeviceClient
import com.gpcombine.assistant.net.FrameRecord
import com.gpcombine.assistant.net.HealthProbe
import com.gpcombine.assistant.net.HealthReport
import com.gpcombine.assistant.proto.DeviceInfo
import com.gpcombine.assistant.proto.EspConfig
import com.gpcombine.assistant.proto.LogCodec
import com.gpcombine.assistant.proto.PairInfo
import com.gpcombine.assistant.store.Prefs
import com.gpcombine.assistant.term.TerminalController
import java.io.File
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull

enum class Phase { IDLE, SCANNING, NEED_CODE, WORKING, READY }

/** 内存轮询的一个采样点：内部堆余 + PSRAM 余（都来自 INFO 回包）。 */
data class MemSample(val tsMs: Long, val ramFree: Long, val psramFree: Long)

data class UiState(
    val phase: Phase = Phase.IDLE,
    val devices: List<ScannedDevice> = emptyList(),
    val deviceName: String = "",
    val info: DeviceInfo? = null,
    val pair: PairInfo? = null,
    val error: String? = null,
    /** 蓝牙栈回调流水账，卡住的时候靠它定位是卡在哪一步。 */
    val trace: List<String> = emptyList(),
    /** 设备推上来的日志（本机时间戳）。屏幕上只留最近 [MAX_LOG_LINES] 行，文件里是全的。 */
    val logs: List<LogLine> = emptyList(),
    /** 暂停时冻住的行号（null = 跟随最新）。 */
    val logPausedAt: Int? = null,
    val logFile: String? = null,
    /** 帧监视器：收发都记，含没人认领的回包。 */
    val frames: List<FrameRecord> = emptyList(),
    val health: HealthReport? = null,
    val healthRunning: Boolean = false,
    val healthError: String? = null,
    val mem: List<MemSample> = emptyList(),
    val memPolling: Boolean = false,
)

class DeviceViewModel(app: Application, private val useFake: Boolean) : AndroidViewModel(app) {
    private val transport: BleTransport =
        if (useFake) FakeTransport() else AndroidBleTransport(app)
    private val client = DeviceClient(transport, viewModelScope, timeoutMs = 4000)
    private val prefs = Prefs(app)
    private val probe = HealthProbe(client, mtu = { transport.mtu.value })
    private val logStore = LogStore(File(app.filesDir, "logs"))

    /** 设置页的状态机（17 字节镜像）。连上并认证后自动读一次。 */
    val config = ConfigController(client, viewModelScope)

    /** 手柄 / 灯光 / 蓝牙 / 配置档：都跑同一套 BLE 命令，连着时各自读一份。 */
    val pad = PadController(client, viewModelScope)
    val led = LedController(client, viewModelScope)
    val bt = BluetoothController(client, viewModelScope, onPairCode = { prefs.pairCode = it })
    val profiles = ProfileController(client, viewModelScope, onConfigChanged = {
        // 加载档会改设备设置：配置页手里那份就过期了，立刻重读
        viewModelScope.launch { config.refresh() }
    })

    /** 终端页：手打命令直接发帧。auth 成功时把配对码记下来，省得再去首页输一遍。 */
    val terminal = TerminalController(
        client = client,
        transport = transport,
        scope = viewModelScope,
        onPairCode = { prefs.pairCode = it },
    )

    private val _ui = MutableStateFlow(UiState())
    val ui: StateFlow<UiState> = _ui.asStateFlow()

    private var scanJob: Job? = null
    private var memJob: Job? = null
    private var logSubscribed = false

    init {
        // 一开机就落盘：掉线/崩溃之后能翻历史，正是"日志落盘"的意义
        runCatching {
            val f = logStore.start(System.currentTimeMillis())
            _ui.update { it.copy(logFile = f.absolutePath) }
        }

        viewModelScope.launch {
            transport.log.collect { line ->
                _ui.update { it.copy(trace = (it.trace + line).takeLast(14)) }
                val l = LogLine(System.currentTimeMillis(), 0, "[stack] $line")
                // 也进日志页：屏幕上、文件里、时间顺序三边一致，出问题只翻一处
                appendLog(l)
                logStore.append(l)
            }
        }

        viewModelScope.launch {
            client.logs.collect { e ->
                val line = LogLine(System.currentTimeMillis(), e.level, e.text)
                appendLog(line)
                logStore.append(line)
            }
        }

        viewModelScope.launch {
            client.frames.collect { r ->
                _ui.update { s -> s.copy(frames = (s.frames + r).takeLast(MAX_FRAMES)) }
            }
        }

        // 设备侧一掉线就会自己退订（见固件 netTick），这边得把标记也清掉，
        // 否则重连后以为"已经订过了"，日志页从此一片空白。
        viewModelScope.launch {
            transport.state.collect { st ->
                if (st != BleState.CONNECTED && logSubscribed) {
                    logSubscribed = false
                    appendLocal("[log] 连接断了，日志订阅失效（重连认证后自动重订）")
                }
                // 设备侧主动断（换配对码 / 关蓝牙 / 掉电）时自己连回来：
                // 用户换个配对码就被踢下线、还得手动回首页重扫一遍，太蠢了。
                if (st == BleState.DISCONNECTED && _ui.value.phase == Phase.READY) maybeReconnect()
            }
        }
    }

    private var reconnectJob: Job? = null

    /** 自动重连：连回来 + 用存着的配对码重新认证。三次不成就放手，让用户回首页。 */
    private fun maybeReconnect() {
        if (useFake) return
        if (reconnectJob?.isActive == true) return
        val addr = prefs.lastAddress ?: return
        val real = transport as? AndroidBleTransport ?: return
        reconnectJob = viewModelScope.launch {
            appendLocal("[ble] 连接断了，自动重连中…")
            repeat(3) { attempt ->
                // 第一次等 900ms：换配对码之后设备那边还要 400ms 才踢人、广播也要重开
                delay(900L * (attempt + 1))
                try {
                    real.connect(addr)
                    val ok = withTimeoutOrNull(10_000) {
                        transport.state.first { it == BleState.CONNECTED }
                    }
                    if (ok != null) {
                        val code = prefs.pairCode
                        if (code != null && client.auth(code)) {
                            appendLocal("[ble] 已自动重连并认证")
                            loadDeviceInfo()
                            return@launch
                        }
                        appendLocal("[ble] 连上了但认证没过（配对码是不是被改了？）")
                    }
                } catch (e: Exception) {
                    appendLocal("[ble] 第 ${attempt + 1} 次重连失败：${e.message}")
                }
            }
            _ui.update { it.copy(error = "掉了之后没连回来，回首页重新扫一次") }
        }
    }

    private fun appendLog(line: LogLine) {
        _ui.update { s ->
            val next = s.logs + line
            val over = next.size - MAX_LOG_LINES
            if (over <= 0) {
                s.copy(logs = next)
            } else {
                // 屏幕缓存满了丢最旧：暂停窗口跟着往前挪，别把界面挪花
                s.copy(
                    logs = next.subList(over, next.size),
                    logPausedAt = s.logPausedAt?.minus(over)?.coerceAtLeast(0),
                )
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
        subscribeLogs()
        // 设置页的数据：连上就先读一份，进"配置"页时不用等
        runCatching { config.refresh() }
        // 手柄/灯光/蓝牙同样先读一份；配置档等进那一页再读（列表读一次就够，没必要占带宽）
        runCatching { pad.refresh() }
        runCatching { led.refresh() }
        runCatching { bt.refresh() }
    }

    /** 连上并认证通过后订阅日志：带 40 行回放，开机那几行（含 USB 自检）就不会漏。 */
    private suspend fun subscribeLogs() {
        if (logSubscribed) return
        runCatching {
            if (client.logSubscribe(LogCodec.SUB_ON_REPLAY, 40)) {
                logSubscribed = true
                appendLocal("[log] 已订阅设备日志（回放 40 行）")
            } else {
                appendLocal("[log] 设备拒绝了日志订阅")
            }
        }.onFailure { appendLocal("[log] 订阅失败：${it.message}") }
    }

    private fun appendLocal(text: String) {
        val line = LogLine(System.currentTimeMillis(), 0, text)
        appendLog(line)
        logStore.append(line)
    }

    // ---- 诊断页 ----

    // ---- 设置页 / 终端页 ----

    fun configEdit(cfg: EspConfig) = config.edit(cfg)
    fun configSave() { viewModelScope.launch { config.save() } }
    fun configReset() { viewModelScope.launch { config.resetToDefaults() } }
    fun configRefresh() { viewModelScope.launch { config.refresh() } }

    /** 离开配置页时把还在 debounce 里的最后一次改动送出去，别让它烂在手里。 */
    fun configFlush() { viewModelScope.launch { config.applyNow() } }

    // ---- 手柄页 ----

    fun padEdit(cfg: com.gpcombine.assistant.proto.PadConfig) = pad.edit(cfg)
    fun padApply() { viewModelScope.launch { pad.apply() } }
    fun padRefresh() { viewModelScope.launch { pad.refresh() } }

    // ---- 灯光页 ----

    fun ledEdit(cfg: com.gpcombine.assistant.proto.LedConfig) = led.edit(cfg)
    fun ledFlush() { viewModelScope.launch { led.applyNow() } }

    // ---- 蓝牙页 ----

    fun btRefresh() { viewModelScope.launch { bt.refresh() } }
    fun btSetName(name: String) { viewModelScope.launch { bt.setName(name) } }
    fun btSetPairCode(code: String) { viewModelScope.launch { bt.setPairCode(code) } }
    fun btRegenerate() { viewModelScope.launch { bt.regenerateCode() } }
    fun btSetEnabled(on: Boolean) { viewModelScope.launch { bt.setEnabled(on) } }

    // ---- 配置档页 ----

    fun profilesRefresh() { viewModelScope.launch { profiles.refresh() } }
    fun profileSave(slot: Int, name: String) { viewModelScope.launch { profiles.save(slot, name) } }
    fun profileLoad(slot: Int) { viewModelScope.launch { profiles.load(slot) } }
    fun profileRename(slot: Int, name: String) { viewModelScope.launch { profiles.rename(slot, name) } }
    fun profileDelete(slot: Int) { viewModelScope.launch { profiles.delete(slot) } }

    fun terminalSend(line: String) = terminal.send(line)
    fun terminalClear() = terminal.clear()
    fun terminalShowPush(on: Boolean) = terminal.setShowPush(on)

    fun setLogPaused(paused: Boolean) {
        _ui.update { s ->
            s.copy(logPausedAt = if (paused) s.logs.size else null)
        }
    }

    fun clearLogs() {
        _ui.update { it.copy(logs = emptyList(), logPausedAt = null) }
    }

    /** 当前会话的落盘文件（导出用）。文件是持续的，导出只是把它分享出去。 */
    fun logFile(): File? = logStore.current

    fun runHealthCheck() {
        if (_ui.value.healthRunning) return
        _ui.update { it.copy(healthRunning = true, healthError = null) }
        viewModelScope.launch {
            try {
                _ui.update { it.copy(health = probe.run(20), healthRunning = false) }
            } catch (e: Exception) {
                _ui.update { it.copy(healthRunning = false, healthError = e.message ?: "体检失败") }
            }
        }
    }

    /** 进入诊断页才开轮询，离开就停——省电也省设备侧的中断。 */
    fun setMemPolling(on: Boolean) {
        memJob?.cancel()
        memJob = null
        _ui.update { it.copy(memPolling = on, mem = if (on) it.mem else emptyList()) }
        if (!on) return

        memJob = viewModelScope.launch {
            while (isActive) {
                runCatching {
                    val info = client.info()
                    _ui.update { s ->
                        val sample = MemSample(System.currentTimeMillis(), info.ramFree, info.psramFree)
                        s.copy(mem = (s.mem + sample).takeLast(MAX_MEM_SAMPLES), info = info)
                    }
                }
                delay(MEM_POLL_MS)
            }
        }
    }

    override fun onCleared() {
        memJob?.cancel()
        logStore.close()
        client.close()
        (transport as? AndroidBleTransport)?.close()
    }

    companion object {
        const val MAX_LOG_LINES = 2000
        const val MAX_FRAMES = 400
        const val MAX_MEM_SAMPLES = 60
        const val MEM_POLL_MS = 2000L

        fun factory(app: Application, useFake: Boolean) = viewModelFactory {
            initializer { DeviceViewModel(app, useFake) }
        }
    }
}
