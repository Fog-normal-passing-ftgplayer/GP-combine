package com.gpcombine.assistant.config

import com.gpcombine.assistant.ble.FakeTransport
import com.gpcombine.assistant.net.DeviceClient
import com.gpcombine.assistant.proto.EspConfig
import com.gpcombine.assistant.proto.Proto
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** 配置页的状态机：假设备（FakeTransport）就是设备端行为的替身，全程真跑帧。 */
class ConfigControllerTest {
    @Test
    fun refreshLoadsDeviceSnapshotAndClearsDirty() = runTest {
        val t = FakeTransport().apply { connect() }
        val c = DeviceClient(t, backgroundScope)
        c.auth("280148")
        val ctrl = ConfigController(c, backgroundScope)

        ctrl.refresh()

        assertFalse("刚读完不该是 dirty", ctrl.state.value.dirty)
        assertEquals(EspConfig.DEFAULT_LAYOUT, ctrl.state.value.cfg.layout)
        assertEquals(100, ctrl.state.value.cfg.backlight)
    }

    /** 拖滑条：三次改动只该发一帧，而且是最后那个值（不然设备被刷屏）。 */
    @Test
    fun draggingSendsOneApplyWithTheLastValue() = runTest {
        val t = FakeTransport().apply { connect() }
        val c = DeviceClient(t, backgroundScope)
        c.auth("280148")
        val ctrl = ConfigController(c, backgroundScope, debounceMs = 300)
        ctrl.refresh()
        val before = t.sent().size

        ctrl.edit(EspConfig(backlight = 40))
        ctrl.edit(EspConfig(backlight = 60))
        ctrl.edit(EspConfig(backlight = 80))
        advanceTimeBy(400)
        runCurrent()
        runCurrent()

        val sent = t.sent().drop(before)
        assertEquals("三次改动应该合并成一帧", 1, sent.size)
        assertEquals(Proto.CMD_CFG_APPLY, sent[0].cmd)
        assertEquals("发的必须是最后那个值", 80, sent[0].payload[5].toInt() and 0xFF)
        assertTrue("改完算 dirty", ctrl.state.value.dirty)
    }

    /** 保存：走 CFG_SET（写 flash），保存完不 dirty；待发的 APPLY 要被取消掉。 */
    @Test
    fun saveWritesFlashAndClearsDirty() = runTest {
        val t = FakeTransport().apply { connect() }
        val c = DeviceClient(t, backgroundScope)
        c.auth("280148")
        val ctrl = ConfigController(c, backgroundScope, debounceMs = 300)
        ctrl.refresh()
        val before = t.sent().size

        ctrl.edit(EspConfig(theme = 3))
        ctrl.save()
        advanceTimeBy(400)
        runCurrent()

        val sent = t.sent().drop(before)
        assertEquals("只该有一条保存帧", 1, sent.size)
        assertEquals(Proto.CMD_CFG_SET, sent[0].cmd)
        assertEquals(3, sent[0].payload[14].toInt() and 0xFF)
        assertFalse("保存完不该再 dirty", ctrl.state.value.dirty)
        assertTrue(ctrl.state.value.justSaved)
    }

    /** 恢复默认：让设备自己写默认值，App 重新读回来，不在本地造默认值。 */
    @Test
    fun resetAsksDeviceAndReloadsDefaults() = runTest {
        val t = FakeTransport().apply { connect() }
        val c = DeviceClient(t, backgroundScope)
        c.auth("280148")
        val ctrl = ConfigController(c, backgroundScope)
        ctrl.refresh()
        ctrl.edit(EspConfig(theme = 5))
        ctrl.save()
        assertEquals(5, ctrl.state.value.cfg.theme)

        ctrl.resetToDefaults()

        assertEquals(1, t.sent().count { it.cmd == Proto.CMD_CFG_RESET })
        assertEquals("默认主题是 0", 0, ctrl.state.value.cfg.theme)
        assertFalse(ctrl.state.value.dirty)
    }

    /** 没读成功（比如还没认证）时，错误要说出来，而且不能把默认值当成设备值标成"已同步"。 */
    @Test
    fun reportsDeviceErrorInsteadOfPretending() = runTest {
        val t = FakeTransport().apply { connect() }
        val c = DeviceClient(t, backgroundScope)
        val ctrl = ConfigController(c, backgroundScope)

        ctrl.refresh()

        assertNotNull("设备回错误必须体现出来", ctrl.state.value.error)
        assertEquals(null, ctrl.state.value.onDevice)
        assertFalse("没读到就不该号称干净", ctrl.state.value.dirty)
    }

    /** 还没读到设备设置也能改（改动照发），不能因为 onDevice 是空就静默丢弃。 */
    @Test
    fun editsArePushedEvenBeforeFirstRead() = runTest {
        val t = FakeTransport().apply { connect() }
        val c = DeviceClient(t, backgroundScope)
        c.auth("280148")
        val ctrl = ConfigController(c, backgroundScope, debounceMs = 300)

        ctrl.edit(EspConfig(wireless = 0))
        advanceTimeBy(400)
        runCurrent()
        runCurrent()

        val applies = t.sent().filter { it.cmd == Proto.CMD_CFG_APPLY }
        assertEquals(1, applies.size)
        assertEquals(0, applies[0].payload[13].toInt() and 0xFF)
    }
}
