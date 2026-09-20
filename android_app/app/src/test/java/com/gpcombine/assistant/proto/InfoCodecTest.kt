package com.gpcombine.assistant.proto

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class InfoCodecTest {
    @Test
    fun parsesInfoFromFirmware() {
        // 格式与固件 netHandleFrame 里的 snprintf 完全一致
        val info = InfoCodec.parseInfo("ver=1.0.0;app=825776;fs=12517376/2540000;ram=67056;psram=5588080")
        assertEquals("1.0.0", info.version)
        assertEquals(825776L, info.appBytes)
        assertEquals(12517376L, info.fsTotal)
        assertEquals(2540000L, info.fsUsed)
        assertEquals(67056L, info.ramFree)
        assertEquals(5588080L, info.psramFree)
    }

    /** 总量和已用写反了会显示成"卡快满了"，专门用两个量级差很大的数钉住顺序。 */
    @Test
    fun fsKeepsTotalBeforeUsed() {
        val info = InfoCodec.parseInfo("ver=v;app=1;fs=100/3;ram=1;psram=1")
        assertEquals(100L, info.fsTotal)
        assertEquals(3L, info.fsUsed)
    }

    @Test
    fun parsesPairInfoFromFirmware() {
        val p = InfoCodec.parsePairInfo("name=GP-Combine-72E0;pair=280148;bt=1;clients=1;ap=0")
        assertEquals("GP-Combine-72E0", p.name)
        assertEquals("280148", p.pairCode)
        assertEquals(true, p.btEnabled)
        assertEquals(1, p.clients)
        assertEquals(false, p.apEnabled)
    }

    @Test
    fun ignoresUnknownKeys() {
        val info = InfoCodec.parseInfo("ver=1;app=1;fs=1/1;ram=1;psram=1;future=42")
        assertEquals("1", info.version)
    }

    @Test
    fun throwsOnMissingField() {
        val e = assertThrows(IllegalArgumentException::class.java) {
            InfoCodec.parseInfo("ver=1;app=1;ram=1;psram=1") // 少了 fs
        }
        assertEquals(true, e.message!!.contains("fs"))
    }
}
