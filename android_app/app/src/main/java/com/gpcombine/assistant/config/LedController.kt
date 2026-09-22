package com.gpcombine.assistant.config

import com.gpcombine.assistant.net.DeviceClient
import com.gpcombine.assistant.proto.LedConfig
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

data class LedState(
    val cfg: LedConfig = LedConfig(),
    val onDevice: LedConfig? = null,
    val loading: Boolean = false,
    val error: String? = null,
) {
    val dirty: Boolean get() = onDevice != null && !cfg.sameAs(onDevice)
}

/**
 * 灯光页：和设置页一样「边调边下发」（300ms debounce）。
 * 灯光改了不会重启设备，改一下立刻能看见效果，正是要的感觉。
 */
class LedController(
    private val client: DeviceClient,
    private val scope: CoroutineScope,
    private val debounceMs: Long = 300,
) {
    private val _state = MutableStateFlow(LedState())
    val state: StateFlow<LedState> = _state.asStateFlow()

    private val lock = Mutex()
    private var applyJob: Job? = null
    /** 最后一次真正发出去的快照（去重用它，不用 dirty：没读到设备值时也得能下发）。 */
    private var lastApplied: LedConfig? = null

    suspend fun refresh() {
        _state.update { it.copy(loading = true, error = null) }
        try {
            val got = client.ledGet()
            if (got == null) {
                _state.update { it.copy(loading = false, error = "设备没给出可识别的灯光设置") }
            } else {
                lastApplied = got
                _state.update { it.copy(cfg = got, onDevice = got, loading = false, error = null) }
            }
        } catch (e: Exception) {
            _state.update { it.copy(loading = false, error = e.message ?: "读灯光设置失败") }
        }
    }

    fun edit(new: LedConfig) {
        _state.update { it.copy(cfg = new.clamp(), error = null) }
        applyJob?.cancel()
        applyJob = scope.launch {
            delay(debounceMs)
            applyNow()
        }
    }

    suspend fun applyNow() {
        val cfg = _state.value.cfg.clamp()
        if (lastApplied != null && cfg.sameAs(lastApplied!!)) return
        lock.withLock {
            try {
                client.ledSet(cfg)
                lastApplied = cfg
                _state.update { it.copy(onDevice = cfg, error = null) }
            } catch (e: Exception) {
                _state.update { it.copy(error = e.message ?: "下发失败") }
            }
        }
    }
}
