package com.gpcombine.assistant.ble

import com.gpcombine.assistant.proto.Frame
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.StateFlow

enum class BleState { IDLE, SCANNING, CONNECTING, CONNECTED, DISCONNECTED }

/**
 * BLE 收发藏在接口后面：真机实现要蓝牙栈和运行时权限，FakeTransport 什么都不需要，
 * 所以 UI 和会话逻辑可以在没有板子的机器上跑测试。
 */
interface BleTransport {
    /** 收帧流。分片重组已经在实现里做完，这里吐出来的一定是完整帧。 */
    val inbound: Flow<Frame>
    val state: StateFlow<BleState>
    suspend fun send(frame: ByteArray)
}
