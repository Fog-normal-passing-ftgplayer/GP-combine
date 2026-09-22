package com.gpcombine.assistant.config

import com.gpcombine.assistant.ble.FakeTransport
import com.gpcombine.assistant.net.DeviceClient
import com.gpcombine.assistant.proto.EspConfig
import com.gpcombine.assistant.proto.Proto
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class BtProfileControllerTest {
    @Test
    fun btRefreshReadsNameCodeAndLink() = runTest {
        val t = FakeTransport().apply { connect() }
        val c = DeviceClient(t, backgroundScope)
        c.auth("280148")
        val ctrl = BluetoothController(c, backgroundScope)

        ctrl.refresh()

        val info = ctrl.state.value.info
        assertNotNull(info)
        assertEquals("GP-Combine-FAKE", info!!.name)
        assertEquals("280148", info.pairCode)
        assertTrue(info.btEnabled)
        assertEquals(2, info.link)
    }

    /** 换配对码：设备会踢人，所以新码必须存进手机（否则自己都连不回去）。 */
    @Test
    fun changingPairCodeStoresItAndFlagsSessionReset() = runTest {
        val t = FakeTransport().apply { connect() }
        val c = DeviceClient(t, backgroundScope)
        c.auth("280148")
        var stored: String? = null
        val ctrl = BluetoothController(c, backgroundScope, onPairCode = { stored = it })

        ctrl.setPairCode("123456")

        assertEquals("123456", stored)
        assertNull("成功时不该有错误", ctrl.state.value.error)
        assertTrue("换了码要提示会话已作废", ctrl.state.value.sessionReset)
        assertEquals("123456", c.pairInfo().pairCode)
    }

    @Test
    fun badPairCodeIsRejectedWithoutSending() = runTest {
        val t = FakeTransport().apply { connect() }
        val c = DeviceClient(t, backgroundScope)
        c.auth("280148")
        val ctrl = BluetoothController(c, backgroundScope)
        val before = t.sent().size

        ctrl.setPairCode("12345")

        assertEquals("参数不合法就不该发帧", before, t.sent().size)
        assertNotNull("要给用户一句人话", ctrl.state.value.error)
        assertEquals("280148", c.pairInfo().pairCode)
    }

    /** 随机换码：新码是设备生成的，App 只能从回包里拿。 */
    @Test
    fun regenerateTakesTheCodeFromTheDevice() = runTest {
        val t = FakeTransport().apply { connect() }
        val c = DeviceClient(t, backgroundScope)
        c.auth("280148")
        var stored: String? = null
        val ctrl = BluetoothController(c, backgroundScope, onPairCode = { stored = it })

        ctrl.regenerateCode()

        assertEquals("135790", stored)
        assertTrue(ctrl.state.value.note.orEmpty().contains("135790"))
        assertTrue(ctrl.state.value.sessionReset)
        assertEquals("设备自己也该换成新码", "135790", c.pairInfo().pairCode)
        assertFalse("换完码旧码就该失效", c.auth("280148"))
        assertTrue("新码才是能用的那个", c.auth("135790"))
    }

    @Test
    fun renamingDeviceKeepsSessionAlive() = runTest {
        val t = FakeTransport().apply { connect() }
        val c = DeviceClient(t, backgroundScope)
        c.auth("280148")
        val ctrl = BluetoothController(c, backgroundScope)

        ctrl.setName("GP-Combine-AB12")

        assertFalse("改名不该作废会话", ctrl.state.value.sessionReset)
        assertEquals("GP-Combine-AB12", c.pairInfo().name)
    }

    // ---- 配置档 ----

    @Test
    fun profileListStartsEmptyAndSaveFillsASlot() = runTest {
        val t = FakeTransport().apply { connect() }
        val c = DeviceClient(t, backgroundScope)
        c.auth("280148")
        val ctrl = ProfileController(c, backgroundScope)

        ctrl.refresh()
        assertEquals(5, ctrl.state.value.slots.size)
        assertTrue("一开始 5 档都该是空的", ctrl.state.value.slots.none { it.used })

        ctrl.save(2, "街机档")
        val slot = ctrl.state.value.slots.first { it.slot == 2 }
        assertTrue(slot.used)
        assertEquals("街机档", slot.name)
        assertNotNull(ctrl.state.value.note)
    }

    /** 关键语义：存进档里的是**设备此刻**的设置，不是 App 手里那份。 */
    @Test
    fun saveCapturesDeviceStateNotAppState() = runTest {
        val t = FakeTransport().apply { connect() }
        val c = DeviceClient(t, backgroundScope)
        c.auth("280148")
        val ctrl = ProfileController(c, backgroundScope)

        c.cfgSet(EspConfig(theme = 3, backlight = 42))
        ctrl.save(1, "A")
        c.cfgSet(EspConfig(theme = 7, backlight = 11))
        ctrl.load(1)

        val after = c.cfgGet()!!
        assertEquals("加载后该回到存那一刻的值", 3, after.theme)
        assertEquals(42, after.backlight)
    }

    /** 改名只动名字，不能把档里存着的那份设置冲掉。 */
    @Test
    fun renameKeepsStoredSettings() = runTest {
        val t = FakeTransport().apply { connect() }
        val c = DeviceClient(t, backgroundScope)
        c.auth("280148")
        val ctrl = ProfileController(c, backgroundScope)

        c.cfgSet(EspConfig(theme = 3))
        ctrl.save(1, "A")
        c.cfgSet(EspConfig(theme = 7))       // 设备设置改成别的
        ctrl.rename(1, "B")
        ctrl.load(1)

        assertEquals("B", ctrl.state.value.slots.first { it.slot == 1 }.name)
        assertEquals("改名不该动档里的设置", 3, c.cfgGet()!!.theme)
    }

    @Test
    fun loadTellsConfigPageToRefresh() = runTest {
        val t = FakeTransport().apply { connect() }
        val c = DeviceClient(t, backgroundScope)
        c.auth("280148")
        var refreshed = 0
        val ctrl = ProfileController(c, backgroundScope, onConfigChanged = { refreshed++ })
        ctrl.save(1, "A")

        ctrl.load(1)

        assertEquals("加载档会改设置，必须让配置页重读", 1, refreshed)
    }

    @Test
    fun deleteEmptiesTheSlot() = runTest {
        val t = FakeTransport().apply { connect() }
        val c = DeviceClient(t, backgroundScope)
        c.auth("280148")
        val ctrl = ProfileController(c, backgroundScope)
        ctrl.save(3, "A")

        ctrl.delete(3)

        assertFalse(ctrl.state.value.slots.first { it.slot == 3 }.used)
    }

    @Test
    fun loadingAnEmptySlotReportsAnError() = runTest {
        val t = FakeTransport().apply { connect() }
        val c = DeviceClient(t, backgroundScope)
        c.auth("280148")
        val ctrl = ProfileController(c, backgroundScope)

        ctrl.load(4)

        assertNotNull("空档要给出人话错误，不能静默", ctrl.state.value.error)
    }
}
