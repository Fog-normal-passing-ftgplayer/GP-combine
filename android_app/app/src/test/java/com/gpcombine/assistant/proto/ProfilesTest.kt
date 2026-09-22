package com.gpcombine.assistant.proto

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * 配置档。名字上限 20 **字节**（中文一个字 3 字节），固件侧
 * `tools/host_tests/fixes_test.cpp::test_profiles` 用的是同一组规则。
 */
class ProfilesTest {
    @Test
    fun parsesTheFirmwareListPayload() {
        val payload = ByteArray(Profiles.SLOTS * Profiles.RECORD_BYTES)
        fun put(i: Int, slot: Int, used: Boolean, name: String) {
            val o = i * Profiles.RECORD_BYTES
            val nb = name.toByteArray(Charsets.UTF_8)
            payload[o] = slot.toByte()
            payload[o + 1] = if (used) 1 else 0
            payload[o + 2] = nb.size.toByte()
            nb.copyInto(payload, o + 3)
        }
        put(0, 1, true, "街机档")
        put(1, 2, false, "")
        put(2, 3, true, "")
        // 设备永远吐满 5 条（没占用的也带槽号），夹具照抄，别留零
        put(3, 4, false, "")
        put(4, 5, false, "")

        val list = Profiles.parseList(payload)!!
        assertEquals(5, list.size)
        assertEquals(1, list[0].slot)
        assertTrue(list[0].used)
        assertEquals("街机档", list[0].name)
        assertFalse(list[1].used)
        assertTrue(list[2].used)
        assertEquals("", list[2].name)
        // 槽号不按顺序时也得对上号（按下标硬认会串档）
        assertEquals(5, list[4].slot)
    }

    @Test
    fun rejectsWrongSizedListPayload() {
        assertNull(Profiles.parseList(ByteArray(Profiles.SLOTS * Profiles.RECORD_BYTES - 1)))
    }

    @Test
    fun nameIsTrimmedAndLimitedToTwentyBytes() {
        assertEquals("街机档", Profiles.sanitizeName("  街机档\n"))
        assertEquals("", Profiles.sanitizeName("   "))
        // 20 字节上限：中文最多 6 个字（18 字节），第 7 个放不下就整字丢掉
        assertEquals("街机档街机档", Profiles.sanitizeName("街机档街机档街"))
        assertEquals(18, Profiles.sanitizeName("街机档街机档街").toByteArray().size)
        // 不能切出半个 UTF-8 字符（切坏了设备上会显示乱码方块）
        val cut = Profiles.sanitizeName("街机档街机档街")
        assertEquals(String(cut.toByteArray(Charsets.UTF_8), Charsets.UTF_8), cut)
    }

    @Test
    fun savePayloadMatchesFirmwareLayout() {
        val p = Profiles.savePayload(3, "街机")
        assertEquals(3, p[0].toInt())
        assertEquals(6, p[1].toInt())
        assertEquals("街机", String(p, 2, p.size - 2, Charsets.UTF_8))
        // 空名字（用设备默认名）也要能发出去
        val q = Profiles.savePayload(1, "")
        assertEquals(1, q[0].toInt())
        assertEquals(0, q[1].toInt())
        assertEquals(2, q.size)
        // 超长名字先截断再发，不能把设备侧的解析撑爆
        val r = Profiles.savePayload(2, "街机档街机档街机档")
        assertTrue(r.size <= 2 + Profiles.NAME_MAX)
    }

    @Test
    fun slotPayloadIsASingleByteAndRejectsBadSlots() {
        assertEquals(1, Profiles.slotPayload(5)!!.size)
        assertEquals(5, Profiles.slotPayload(5)!![0].toInt())
        assertNull(Profiles.slotPayload(0))
        assertNull(Profiles.slotPayload(6))
    }
}
