package com.gpcombine.assistant.config

import com.gpcombine.assistant.net.DeviceClient
import com.gpcombine.assistant.proto.EspConfig
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

data class ConfigState(
    /** 界面正在编辑的快照（实时下发用的就是它）。 */
    val cfg: EspConfig = EspConfig(),
    /** 设备上那份（读到或写成功的），用来算 dirty。null = 还没读到，别乱标"已修改"。 */
    val onDevice: EspConfig? = null,
    val loading: Boolean = false,
    val saving: Boolean = false,
    val error: String? = null,
    /** 刚保存成功，界面给个"已写入设备"的提示。 */
    val justSaved: Boolean = false,
) {
    val dirty: Boolean get() = onDevice != null && !cfg.clamp().sameAs(onDevice)
}

/**
 * 设备设置页的状态机。
 *
 * 语义刻意和设备菜单一致（见固件里 VIEW_SUB 的 save-confirm 那段）：
 * - 控件一改 → 300ms debounce 后走 `CFG_APPLY`（**只应用不写 flash**），设备屏幕立刻变
 * - 点"保存到设备" → 走 `CFG_SET`（应用 + 落 LittleFS + 镜像给 Pico），这时才算干净
 * - "恢复默认" → `CFG_RESET`，然后重新读一遍（默认值以设备为准，不在 App 里硬编码一份）
 *
 * 一条串行锁：BLE 那边一次只推一帧，并发下发只会堆在设备接收队列里。
 */
class ConfigController(
    private val client: DeviceClient,
    private val scope: CoroutineScope,
    private val debounceMs: Long = 300,
) {
    private val _state = MutableStateFlow(ConfigState())
    val state: StateFlow<ConfigState> = _state.asStateFlow()

    private val lock = Mutex()
    private var applyJob: Job? = null

    /**
     * 最后一次真正发给设备的快照。用它去重，而不是用 dirty：
     * "还没读到设备设置"时也该能把改动推下去，不能因为 dirty 算不出来就静默丢弃。
     */
    private var lastApplied: EspConfig? = null

    /** 读设备当前设置（进配置页、或设备端菜单改完之后调用）。 */
    suspend fun refresh() {
        _state.update { it.copy(loading = true, error = null) }
        try {
            val got = client.cfgGet()
            if (got == null) {
                _state.update { it.copy(loading = false, error = "设备没给出可识别的设置镜像") }
            } else {
                lastApplied = got
                _state.update {
                    it.copy(cfg = got, onDevice = got, loading = false, error = null, justSaved = false)
                }
            }
        } catch (e: Exception) {
            _state.update { it.copy(loading = false, error = e.message ?: "读设置失败") }
        }
    }

    /** 控件改动：本地立刻生效，下发推迟到 [debounceMs] 之后（拖滑条不会给设备刷帧）。 */
    fun edit(new: EspConfig) {
        _state.update { it.copy(cfg = new.clamp(), justSaved = false) }
        applyJob?.cancel()
        applyJob = scope.launch {
            delay(debounceMs)
            applyNow()
        }
    }

    /** 不等 debounce 直接下发（离开页面时调一次，免得最后一次改动没送到）。 */
    suspend fun applyNow() {
        val cfg = _state.value.cfg.clamp()
        if (lastApplied != null && cfg.sameAs(lastApplied!!)) return
        lock.withLock {
            try {
                client.cfgApply(cfg)
                lastApplied = cfg
                _state.update { it.copy(error = null) }
            } catch (e: Exception) {
                _state.update { it.copy(error = e.message ?: "下发失败") }
            }
        }
    }

    /** 保存到设备：应用 + 写 flash。 */
    suspend fun save() {
        applyJob?.cancel()
        val cfg = _state.value.cfg.clamp()
        _state.update { it.copy(saving = true, error = null) }
        try {
            lock.withLock { client.cfgSet(cfg) }
            lastApplied = cfg
            _state.update {
                it.copy(cfg = cfg, onDevice = cfg, saving = false, justSaved = true, error = null)
            }
        } catch (e: Exception) {
            _state.update { it.copy(saving = false, error = e.message ?: "保存失败") }
        }
    }

    /** 恢复默认：让设备自己写默认值，然后重新读回来（不在 App 里再造一份默认值）。 */
    suspend fun resetToDefaults() {
        applyJob?.cancel()
        _state.update { it.copy(saving = true, error = null) }
        try {
            lock.withLock { client.cfgReset() }
            lastApplied = null
            _state.update { it.copy(saving = false) }
            refresh()
        } catch (e: Exception) {
            _state.update { it.copy(saving = false, error = e.message ?: "恢复默认失败") }
        }
    }

    fun clearJustSaved() = _state.update { it.copy(justSaved = false) }
}
