package com.gpcombine.assistant.proto

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * 载荷要和固件 `fixes_test.cpp::test_proto_bt_set` 里那条夹具逐字节一致 ——
 * 固件就是拿那串字节当"正规载荷"验的。
 */
class BtSetTest {
    @Test
    fun matchingTheFirmwareFixture() {
        val p = BtSet.payload(name = "GP-Combine-7", pairCode = "280148", btOn = true)!!
        assertEquals(0x07, p[0].toInt() and 0xFF)
        assertEquals(1, p[1].toInt() and 0xFF)
        assertEquals(12, p[2].toInt() and 0xFF)
        assertEquals("GP-Combine-7", String(p, 3, 12, Charsets.UTF_8))
        assertEquals(6, p[15].toInt() and 0xFF)
        assertEquals("280148", String(p, 16, 6, Charsets.US_ASCII))
        assertEquals(22, p.size)
    }

    @Test
    fun onlySomeFieldsSet() {
        val sw = BtSet.payload(btOn = false)!!
        assertArrayEquals(byteArrayOf(BtSet.FLAG_SW.toByte(), 0, 0, 0), sw)

        val nameOnly = BtSet.payload(name = "ABC")!!
        assertEquals(BtSet.FLAG_NAME, nameOnly[0].toInt() and 0xFF)
        assertEquals("ABC", String(nameOnly, 3, 3, Charsets.UTF_8))
        assertEquals(0, nameOnly[6].toInt() and 0xFF)   // 不带配对码段
        assertEquals(7, nameOnly.size)
    }

    @Test
    fun rejectsNothingToDoAndBadArguments() {
        // 注意 JUnit 的两个参数是 (消息, 值)：写反了会变成"拿 ByteArray 当 String 用"的编译错误
        assertNull("什么都不改就别发帧", BtSet.payload())
        assertNull("空名字该拒绝", BtSet.payload(name = ""))
        assertNull("超 20 字节该拒绝", BtSet.payload(name = "x".repeat(BtSet.NAME_MAX + 1)))
        assertNull("5 位配对码该拒绝", BtSet.payload(pairCode = "28014"))
        assertNull("带字母的配对码该拒绝", BtSet.payload(pairCode = "28014a"))
        assertTrue(BtSet.pairCodeValid("000000"))
        assertFalse(BtSet.pairCodeValid("28014"))
    }

    /** 中文名字按字节算长度，设备也是按字节读的。 */
    @Test
    fun chineseNameLengthIsBytes() {
        val p = BtSet.payload(name = "街机")!!
        assertEquals(6, p[2].toInt() and 0xFF)
        assertEquals("街机", String(p, 3, 6, Charsets.UTF_8))
    }
}
