package com.gpcombine.assistant.config

import com.gpcombine.assistant.ble.FakeTransport
import com.gpcombine.assistant.net.DeviceClient
import com.gpcombine.assistant.proto.LedConfig
import com.gpcombine.assistant.proto.PadConfig
import com.gpcombine.assistant.proto.Proto
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** 手柄/灯光页的状态机：假设备就是设备端行为的替身，全程真跑帧。 */
class PadLedControllerTest {
    @Test
    fun padRefreshReadsDeviceValues() = runTest {
        val t = FakeTransport().apply { connect() }
        val c = DeviceClient(t, backgroundScope)
        c.auth("280148")
        val ctrl = PadController(c, backgroundScope)

        ctrl.refresh()

        assertNotNull(ctrl.state.value.onDevice)
        assertFalse("刚读完不该是 dirty", ctrl.state.value.dirty)
        assertEquals(PadConfig().debounce, ctrl.state.value.cfg.debounce)
    }

    /** 手柄页不边改边下发：改了必须点"应用"才发帧（换输入模式会重启 Pico）。 */
    @Test
    fun padEditSendsNothingUntilApply() = runTest {
        val t = FakeTransport().apply { connect() }
        val c = DeviceClient(t, backgroundScope)
        c.auth("280148")
        val ctrl = PadController(c, backgroundScope)
        ctrl.refresh()
        val before = t.sent().size

        ctrl.edit(PadConfig(inputMode = 5, socdMode = 2))
        advanceTimeBy(1000)
        runCurrent()
        assertEquals("没点应用就不该发帧", before, t.sent().size)
        assertTrue("改了要算 dirty", ctrl.state.value.dirty)

        ctrl.apply()
        val sent = t.sent().drop(before)
        assertEquals(1, sent.size)
        assertEquals(Proto.CMD_GP_SET, sent[0].cmd)
        assertEquals(5, sent[0].payload[0].toInt() and 0xFF)
        assertEquals(2, sent[0].payload[1].toInt() and 0xFF)
        assertFalse("下发完不该再 dirty", ctrl.state.value.dirty)
        // 设备那边真的收下了（不是只发出去就算）
        assertEquals(5, c.padGet()!!.inputMode)
    }

    @Test
    fun padApplyWarnsAboutPicoRestartOnlyWhenInputModeChanges() = runTest {
        val t = FakeTransport().apply { connect() }
        val c = DeviceClient(t, backgroundScope)
        c.auth("280148")
        val ctrl = PadController(c, backgroundScope)
        ctrl.refresh()

        ctrl.edit(PadConfig(debounce = 9))
        ctrl.apply()
        val noRestart = ctrl.state.value.note.orEmpty()
        assertFalse("只改去抖不该说要重启：$noRestart", noRestart.contains("重启"))

        ctrl.edit(PadConfig(inputMode = 3, debounce = 9))
        ctrl.apply()
        assertTrue("换输入模式必须提示设备会重启", ctrl.state.value.note.orEmpty().contains("重启"))
    }

    /** 拖速度滑条：三次改动合并成一帧，而且是最后那个值。 */
    @Test
    fun ledDragMergesIntoOneFrameWithTheLastValue() = runTest {
        val t = FakeTransport().apply { connect() }
        val c = DeviceClient(t, backgroundScope)
        c.auth("280148")
        val ctrl = LedController(c, backgroundScope, debounceMs = 300)
        ctrl.refresh()
        val before = t.sent().size

        ctrl.edit(LedConfig(chaseSpeed = 40))
        ctrl.edit(LedConfig(chaseSpeed = 60))
        ctrl.edit(LedConfig(chaseSpeed = 80))
        advanceTimeBy(400)
        runCurrent()

        val sent = t.sent().drop(before)
        assertEquals("三次改动应该合并成一帧", 1, sent.size)
        assertEquals(Proto.CMD_LED_SET, sent[0].cmd)
        assertEquals(80, sent[0].payload[4].toInt() and 0xFF)
        assertEquals("设备那边也该是最后那个值", 80, c.ledGet()!!.chaseSpeed)
    }

    @Test
    fun ledFlushSendsPendingChangeImmediately() = runTest {
        val t = FakeTransport().apply { connect() }
        val c = DeviceClient(t, backgroundScope)
        c.auth("280148")
        val ctrl = LedController(c, backgroundScope, debounceMs = 3000)
        ctrl.refresh()
        val before = t.sent().size

        ctrl.edit(LedConfig(brightness = 1))
        ctrl.applyNow()   // 离开页面时调的就是它

        val sent = t.sent().drop(before)
        assertEquals(1, sent.size)
        assertEquals(1, sent[0].payload[1].toInt() and 0xFF)
        assertEquals(1, c.ledGet()!!.brightness)
    }
}
