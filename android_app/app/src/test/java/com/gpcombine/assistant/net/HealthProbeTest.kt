package com.gpcombine.assistant.net

import com.gpcombine.assistant.ble.BleState
import com.gpcombine.assistant.ble.BleTransport
import com.gpcombine.assistant.ble.FakeTransport
import com.gpcombine.assistant.proto.Frame
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class HealthProbeTest {
    private fun TestScope.client(t: BleTransport) = DeviceClient(t, backgroundScope, timeoutMs = 50)

    /** 单调递增的假时钟：每问一次走 5 ms，算出来的延迟就是确定的。 */
    private fun tickingClock(): () -> Long {
        var now = 0L
        return { now += 5; now }
    }

    @Test
    fun reportsPingStatsMtuAndInfoSize() = runTest {
        val t = FakeTransport().apply { connect() }
        val c = client(t)
        assertTrue(c.auth("280148"))

        val r = HealthProbe(c, { 247 }, tickingClock()).run(rounds = 4)

        assertEquals(4, r.rounds)
        assertEquals("假设备每次都回，不该有丢包", 4, r.ok)
        assertEquals(0, r.lost)
        assertEquals(5, r.minMs)
        assertEquals(5, r.avgMs)
        assertEquals(5, r.maxMs)
        assertEquals(247, r.mtu)
        assertTrue("INFO 回包应该有内容", r.infoBytes > 0)
        assertEquals("247-3=244 够装下整帧，应该只有 1 片", 1, r.infoChunks)
        assertEquals("0.0.0-fake", r.info?.version)
    }

    /** MTU 只协商到 23 时，同一帧要分很多片 —— 体检必须把这件事显出来。 */
    @Test
    fun smallMtuShowsManyChunks() = runTest {
        val t = FakeTransport().apply { connect() }
        val c = client(t)
        c.auth("280148")

        val r = HealthProbe(c, { 23 }, tickingClock()).run(rounds = 1)

        assertEquals(23, r.mtu)
        assertTrue("20 字节一片时应该明显多于 1 片，得到 ${r.infoChunks}", r.infoChunks > 3)
    }

    /** 设备不回包：全部算丢包，不能崩、也不能把 min/avg 算成 0 以外的怪值。 */
    @Test
    fun silentDeviceCountsAsLost() = runTest {
        val silent = object : BleTransport {
            override val inbound: Flow<Frame> = MutableSharedFlow<Frame>()
            override val state: StateFlow<BleState> = MutableStateFlow(BleState.CONNECTED)
            override val log: Flow<String> = MutableSharedFlow<String>()
            override val mtu: StateFlow<Int> = MutableStateFlow(23)
            override suspend fun send(frame: ByteArray) = Unit
        }

        val r = HealthProbe(client(silent), { 23 }, { 0L }).run(rounds = 3)

        assertEquals(3, r.rounds)
        assertEquals(0, r.ok)
        assertEquals(3, r.lost)
        assertEquals(0, r.minMs)
        assertEquals(0, r.infoBytes)
        assertEquals(null, r.info)
    }
}
