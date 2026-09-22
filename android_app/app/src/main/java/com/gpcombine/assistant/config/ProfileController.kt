package com.gpcombine.assistant.config

import com.gpcombine.assistant.net.DeviceClient
import com.gpcombine.assistant.proto.Profiles
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

data class ProfileState(
    val slots: List<Profiles.Entry> = emptyList(),
    val loading: Boolean = false,
    val busy: Boolean = false,
    val error: String? = null,
    val note: String? = null,
)

/**
 * 配置档页（`/profiles/1..5.cfg`）。
 *
 * 关键语义：**存进档里的是"设备此刻的设置"，不是 App 手里那份**。
 * 两边版本不一致时以设备为准 —— 否则 App 里没读到的旧值会被写进档里。
 * 加载档之后设备设置会变，所以要让设置页重新读一遍（[onConfigChanged]）。
 */
class ProfileController(
    private val client: DeviceClient,
    private val scope: CoroutineScope,
    private val onConfigChanged: () -> Unit = {},
) {
    private val _state = MutableStateFlow(ProfileState())
    val state: StateFlow<ProfileState> = _state.asStateFlow()

    private val lock = Mutex()

    suspend fun refresh() {
        _state.update { it.copy(loading = true, error = null) }
        try {
            val got = client.profiles()
            if (got == null) {
                _state.update { it.copy(loading = false, error = "设备没给出可识别的配置档列表") }
            } else {
                _state.update { it.copy(slots = got, loading = false, error = null) }
            }
        } catch (e: Exception) {
            _state.update { it.copy(loading = false, error = e.message ?: "读配置档失败") }
        }
    }

    suspend fun save(slot: Int, name: String) = run("存配置档失败") {
        if (!client.profileSave(slot, name)) throw IllegalArgumentException("档位不合法")
        "已把设备当前设置存进档$slot"
    }

    suspend fun load(slot: Int) = run("加载配置档失败") {
        if (!client.profileLoad(slot)) throw IllegalArgumentException("档位不合法")
        onConfigChanged()
        "已加载档$slot：设备设置已按档里的内容改了"
    }

    suspend fun rename(slot: Int, name: String) = run("改名失败") {
        if (!client.profileRename(slot, name)) throw IllegalArgumentException("档位不合法")
        "档$slot 已改名（档里的设置没动）"
    }

    suspend fun delete(slot: Int) = run("删档失败") {
        if (!client.profileDelete(slot)) throw IllegalArgumentException("档位不合法")
        "档$slot 已删除"
    }

    private suspend fun run(ifFail: String, body: suspend () -> String) {
        _state.update { it.copy(busy = true, error = null, note = null) }
        try {
            val note = lock.withLock { body() }
            val fresh = runCatching { client.profiles() }.getOrNull()
            _state.update {
                it.copy(busy = false, note = note, error = null, slots = fresh ?: it.slots)
            }
        } catch (e: Exception) {
            _state.update { it.copy(busy = false, error = e.message ?: ifFail, note = null) }
        }
    }

    fun clearNote() = _state.update { it.copy(note = null) }
}
