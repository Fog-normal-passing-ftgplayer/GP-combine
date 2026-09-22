package com.gpcombine.assistant.config

import com.gpcombine.assistant.net.DeviceClient
import com.gpcombine.assistant.proto.PairInfo
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

data class BtState(
    val info: PairInfo? = null,
    val loading: Boolean = false,
    val busy: Boolean = false,
    val error: String? = null,
    val note: String? = null,
    /**
     * 改了配对码/清了配对：当前这条 BLE 会话马上就要断，界面据此显示
     * "设备正在重连"，别让用户以为是 App 崩了。
     */
    val sessionReset: Boolean = false,
)

/**
 * 蓝牙页。
 *
 * 三条命令的后果差别很大，界面上必须说清楚：
 *  * 改设备名 —— 只重启广播，已连的手机不受影响
 *  * 改/换配对码 —— 设备作废当前会话（换码不踢人等于没换），App 得用新码重连
 *  * 关蓝牙开关 —— 广播停掉，已连的手机断开；同时 nRF 那边按「无线开关」恢复
 */
class BluetoothController(
    private val client: DeviceClient,
    private val scope: CoroutineScope,
    /** 新配对码要存进手机：换完自己都连不回去就没意义了。 */
    private val onPairCode: (String) -> Unit = {},
) {
    private val _state = MutableStateFlow(BtState())
    val state: StateFlow<BtState> = _state.asStateFlow()

    private val lock = Mutex()
    /** 本次操作要不要把"会话已被作废"这个提示亮出来（在 [run] 里读）。 */
    private var markSessionReset = false

    suspend fun refresh() {
        _state.update { it.copy(loading = true, error = null) }
        try {
            val got = client.pairInfo()
            _state.update { it.copy(info = got, loading = false, error = null) }
        } catch (e: Exception) {
            _state.update { it.copy(loading = false, error = e.message ?: "读蓝牙信息失败") }
        }
    }

    /** 改设备名。名字会被固件清洗/截断，界面回读一次以设备为准。 */
    suspend fun setName(name: String) = run(ifFail = "改名失败") {
        client.btSet(name = name)
        "设备名已改（广播已重启，正在连的手机不受影响）"
    }

    /** 自定义配对码。换完设备会踢掉所有手机，App 拿新码自己重连。 */
    suspend fun setPairCode(code: String) = run(ifFail = "换配对码失败") {
        require(code.length == 6 && code.all { it in '0'..'9' }) { "配对码必须是 6 位数字" }
        if (!client.btSet(pairCode = code)) throw IllegalArgumentException("配对码不合法")
        onPairCode(code)
        markSessionReset = true
        "配对码已换：设备会断开所有手机，App 会用新码自己连回来"
    }

    /** 让设备随机生成一个新配对码（码从设备回包里拿，不在这里造）。 */
    suspend fun regenerateCode() = run(ifFail = "换配对码失败") {
        val fresh = client.btClear()
        require(fresh.length == 6 && fresh.all { it in '0'..'9' }) {
            "设备回的新配对码不是 6 位数字：$fresh"
        }
        onPairCode(fresh)
        markSessionReset = true
        "新配对码 $fresh（设备会断开所有手机，App 会用新码自己连回来）"
    }

    suspend fun setEnabled(on: Boolean) = run(ifFail = "蓝牙开关失败") {
        if (!client.btSet(btOn = on)) throw IllegalArgumentException("参数不合法")
        if (!on) markSessionReset = true
        if (on) "蓝牙已开：nRF 无线手柄输出让位（两者互斥）" else "蓝牙已关：手机都会掉线，nRF 按「无线开关」恢复"
    }

    /** 公用的"忙 → 发命令 → 回读 + 记提示"骨架。 */
    private suspend fun run(ifFail: String, body: suspend () -> String): Unit {
        _state.update { it.copy(busy = true, error = null, note = null) }
        markSessionReset = false
        try {
            val note = lock.withLock { body() }
            val fresh = runCatching { client.pairInfo() }.getOrNull()
            _state.update {
                it.copy(
                    busy = false,
                    note = note,
                    error = null,
                    sessionReset = markSessionReset,
                    info = fresh ?: it.info,
                )
            }
        } catch (e: Exception) {
            _state.update {
                it.copy(busy = false, error = e.message ?: ifFail, note = null)
            }
        }
    }

    fun clearNote() = _state.update { it.copy(note = null, sessionReset = false) }
}
