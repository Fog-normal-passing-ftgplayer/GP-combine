package com.gpcombine.assistant.net

import com.gpcombine.assistant.ble.BleState
import com.gpcombine.assistant.ble.BleTransport
import com.gpcombine.assistant.ble.FakeTransport
import com.gpcombine.assistant.proto.Frame
import com.gpcombine.assistant.proto.FrameParser
import com.gpcombine.assistant.proto.Proto
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DeviceClientTest {
    private fun TestScope.client(t: BleTransport) = DeviceClient(t, backgroundScope, timeoutMs = 1000)

    @Test
    fun pingRoundTrip() = runTest {
        val t = FakeTransport().apply { connect() }
        assertTrue(client(t).ping())
    }

    @Test
    fun authAcceptsOnlyTheRightCode() = runTest {
        val t = FakeTransport("280148").apply { connect() }
        val c = client(t)
        assertFalse("错的码必须返回 false", c.auth("000000"))
        assertTrue("对的码必须返回 true", c.auth("280148"))
    }

    @Test
    fun infoParsesAfterAuth() = runTest {
        val t = FakeTransport().apply { connect() }
        val c = client(t)
        c.auth("280148")
        assertEquals("0.0.0-fake", c.info().version)
        assertEquals(12517376L, c.info().fsTotal)
    }

    /** 没认证就查 INFO，设备回 ERR_NOT_AUTHED，客户端要把它变成带错误码的异常。 */
    @Test
    fun unauthenticatedCommandRaisesDeviceException() = runTest {
        val t = FakeTransport().apply { connect() }
        val c = client(t)
        val e = runCatching { c.info() }.exceptionOrNull()
        assertTrue("应该是 DeviceException，实际 $e", e is DeviceException)
        assertEquals(Proto.ERR_NOT_AUTHED, (e as DeviceException).code)
    }

    @Test
    fun timesOutWhenDeviceNeverAnswers() = runTest {
        val silent = object : BleTransport {
            override val inbound = MutableSharedFlow<Frame>()
            override val state = MutableStateFlow(BleState.CONNECTED)
            override val log = MutableSharedFlow<String>()
            override suspend fun send(frame: ByteArray) = Unit
        }
        val e = runCatching { client(silent).ping() }.exceptionOrNull()
        assertTrue("应该是超时，实际 $e", e is TimeoutCancellationException)
    }

    /** seq 必须自增，否则两次请求的回包会互相串台。 */
    @Test
    fun seqIncrementsBetweenRequests() = runTest {
        val seen = mutableListOf<Int>()
        val t = object : BleTransport {
            override val inbound = MutableSharedFlow<Frame>()
            override val state = MutableStateFlow(BleState.CONNECTED)
            override val log = MutableSharedFlow<String>()
            override suspend fun send(frame: ByteArray) {
                val p = FrameParser()
                frame.forEach { b -> p.push(b)?.let { f -> seen += f.seq } }
            }
        }
        val c = DeviceClient(t, backgroundScope, timeoutMs = 50)
        // 这个 transport 不回包，三次请求必然超时；本用例只关心发出去的 seq
        runCatching { c.ping() }
        runCatching { c.ping() }
        runCatching { c.ping() }
        assertEquals(listOf(0, 1, 2), seen)
    }
}
