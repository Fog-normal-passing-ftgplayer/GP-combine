package com.gpcombine.assistant.config

import com.gpcombine.assistant.net.DeviceClient
import com.gpcombine.assistant.proto.PadConfig
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

data class PadState(
    val cfg: PadConfig = PadConfig(),
    /** 设备上那份（读到或写成功的），null = 还没读到。 */
    val onDevice: PadConfig? = null,
    val loading: Boolean = false,
    val applying: Boolean = false,
    val error: String? = null,
    /** 给用户的提示（"已下发"、"换了输入模式设备会重启"）。 */
    val note: String? = null,
) {
    val dirty: Boolean get() = onDevice != null && cfg.clamp() != onDevice
}

/**
 * 手柄页的状态机。
 *
 * 和设备菜单其它页**不一样**：这里不边改边下发。换输入模式会让 Pico 立刻重启
 * （输入模式在驱动启动时才应用），用户拨一下 ◀ 就重启一次显然不行。
 * 所以是「改 → 点应用到设备 → 一次性下发」。
 */
class PadController(private val client: DeviceClient, private val scope: CoroutineScope) {
    private val _state = MutableStateFlow(PadState())
    val state: StateFlow<PadState> = _state.asStateFlow()

    private val lock = Mutex()

    suspend fun refresh() {
        _state.update { it.copy(loading = true, error = null) }
        try {
            val got = client.padGet()
            if (got == null) {
                _state.update { it.copy(loading = false, error = "设备没给出可识别的手柄设置") }
            } else {
                _state.update {
                    it.copy(cfg = got, onDevice = got, loading = false, error = null, note = null)
                }
            }
        } catch (e: Exception) {
            _state.update { it.copy(loading = false, error = e.message ?: "读手柄设置失败") }
        }
    }

    fun edit(new: PadConfig) =
        _state.update { it.copy(cfg = new.clamp(), note = null, error = null) }

    suspend fun apply() {
        val before = _state.value.onDevice
        val cfg = _state.value.cfg.clamp()
        _state.update { it.copy(applying = true, error = null) }
        try {
            lock.withLock { client.padSet(cfg) }
            val reboot = before != null && cfg.rebootsDeviceComparedTo(before)
            _state.update {
                it.copy(
                    applying = false,
                    onDevice = cfg,
                    error = null,
                    note = if (reboot) {
                        "已下发：输入模式换了，设备会自己重启一下（1~2 秒）"
                    } else {
                        "已下发到设备"
                    },
                )
            }
        } catch (e: Exception) {
            _state.update { it.copy(applying = false, error = e.message ?: "下发失败") }
        }
    }

    /** 离开页面时清掉提示，别让"已下发"一直挂在屏幕上。 */
    fun clearNote() = _state.update { it.copy(note = null) }
}
