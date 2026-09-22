package com.gpcombine.assistant.net

import com.gpcombine.assistant.ble.BleState
import com.gpcombine.assistant.ble.BleTransport
import com.gpcombine.assistant.ble.FakeTransport
import com.gpcombine.assistant.proto.Frame
import com.gpcombine.assistant.proto.FrameParser
import com.gpcombine.assistant.proto.LogCodec
import com.gpcombine.assistant.proto.Proto
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.flow.StateFlow
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
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
            override val mtu = MutableStateFlow(23)
            override suspend fun send(frame: ByteArray) = Unit
        }
        val e = runCatching { client(silent).ping() }.exceptionOrNull()
        assertTrue("应该是超时，实际 $e", e is TimeoutCancellationException)
    }

    /** 手动投帧的 transport：设备主动推（0x86）那条路只有它能造出来。 */
    private class ManualTransport : BleTransport {
        private val _in = MutableSharedFlow<Frame>(extraBufferCapacity = 32)
        override val inbound: Flow<Frame> = _in.asSharedFlow()
        override val state: StateFlow<BleState> = MutableStateFlow(BleState.CONNECTED)
        override val log: Flow<String> = MutableSharedFlow<String>()
        override val mtu: StateFlow<Int> = MutableStateFlow(247)
        val sent = mutableListOf<Frame>()

        fun emit(f: Frame) {
            _in.tryEmit(f)
        }

        override suspend fun send(frame: ByteArray) {
            val p = FrameParser()
            frame.forEach { b -> p.push(b)?.let { sent += it } }
        }
    }

    /** 设备主动推的日志帧：seq=0、cmd=0x86，等不到 pending，必须走 logs 而不是被丢掉。 */
    @Test
    fun devicePushLogReachesLogsFlow() = runTest {
        val t = ManualTransport()
        val c = DeviceClient(t, backgroundScope, timeoutMs = 1000)
        val got = mutableListOf<String>()
        // Unconfined：collect 立刻生效，不然 emit 的那一刻还没订阅上，值会被直接丢掉
        backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) {
            c.logs.collect { got += it.text }
        }
        // 实测：backgroundScope 里的任务不吃 advanceUntilIdle（探针里 subscriber 一直是 0），
        // runCurrent 才会真的把它们跑起来 —— 客户端那个 collector 得先订阅上 inbound。
        runCurrent()

        t.emit(Frame(Proto.CMD_LOG_EVT, 0, byteArrayOf(0) + "boot ok".toByteArray()))
        t.emit(Frame(Proto.CMD_LOG_EVT, 0, byteArrayOf(0) + "[ble] clients=1".toByteArray()))
        runCurrent()

        assertEquals(listOf("boot ok", "[ble] clients=1"), got)
    }

    /** 收不到匹配请求的回包（迟到/重放）不能静默消失，至少要进帧监视器。 */
    @Test
    fun unmatchedReplyIsRecordedNotSwallowed() = runTest {
        val t = ManualTransport()
        val c = DeviceClient(t, backgroundScope, timeoutMs = 1000)
        val recs = mutableListOf<FrameRecord>()
        backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) {
            c.frames.collect { recs += it }
        }
        runCurrent()

        t.emit(Frame(Proto.CMD_INFO, 4242, "x".toByteArray()))
        runCurrent()

        assertEquals(1, recs.size)
        assertEquals(Dir.RX, recs[0].dir)
        assertEquals(4242, recs[0].seq)
        assertTrue("要留下'没人认领'的说明，得到：${recs[0].note}", recs[0].note.isNotEmpty())
    }

    /** 收发都要进帧监视器：TX 一条、RX 一条。 */
    @Test
    fun framesRecordBothDirections() = runTest {
        val t = FakeTransport().apply { connect() }
        val c = client(t)
        val recs = mutableListOf<FrameRecord>()
        backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) {
            c.frames.collect { recs += it }
        }
        advanceUntilIdle()

        c.ping()
        advanceUntilIdle()

        assertEquals(listOf(Dir.TX, Dir.RX), recs.map { it.dir })
        assertEquals(Proto.CMD_PING, recs[0].cmd)
        assertEquals(0, recs[0].seq)
        assertEquals("PING", FrameRecord.cmdName(recs[0].cmd))
    }

    /** LOG_SUB 的载荷必须和固件 protoParseLogSub 对上：mode + 回放行数。 */
    @Test
    fun logSubscribeSendsFirmwareLayout() = runTest {
        val t = ManualTransport()
        val c = DeviceClient(t, backgroundScope, timeoutMs = 50)
        runCatching { c.logSubscribe(LogCodec.SUB_ON_REPLAY, 8) }
        assertEquals(1, t.sent.size)
        assertEquals(Proto.CMD_LOG_SUB, t.sent[0].cmd)
        assertEquals(LogCodec.SUB_ON_REPLAY, t.sent[0].payload[0].toInt())
        assertEquals(8, t.sent[0].payload[1].toInt())
    }

    /** seq 必须自增，否则两次请求的回包会互相串台。 */
    @Test
    fun seqIncrementsBetweenRequests() = runTest {
        val seen = mutableListOf<Int>()
        val t = object : BleTransport {
            override val inbound = MutableSharedFlow<Frame>()
            override val state = MutableStateFlow(BleState.CONNECTED)
            override val log = MutableSharedFlow<String>()
            override val mtu = MutableStateFlow(23)
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
