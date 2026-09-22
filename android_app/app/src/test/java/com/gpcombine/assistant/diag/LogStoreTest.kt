package com.gpcombine.assistant.diag

import java.io.File
import java.nio.file.Files
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class LogStoreTest {
    private fun tmp(): File = Files.createTempDirectory("gplog").toFile()

    /** 本机时区下的一个固定时刻：2026-09-22 13:04:05.123 */
    private fun ts(y: Int, mo: Int, d: Int, h: Int, mi: Int, s: Int, ms: Int): Long =
        java.time.ZonedDateTime.of(y, mo, d, h, mi, s, ms * 1_000_000, java.time.ZoneId.systemDefault())
            .toInstant().toEpochMilli()

    @Test
    fun lineCarriesStampAndLevel() {
        val l = LogLine(ts(2026, 9, 22, 13, 4, 5, 123), 2, "[ble] clients=1")
        assertEquals("2026-09-22 13:04:05.123 [E] [ble] clients=1", LogFormat.line(l))
        assertEquals("I", LogFormat.tag(0))
        assertEquals("W", LogFormat.tag(1))
    }

    @Test
    fun filterIgnoresCaseAndBlankKeyword() {
        val l = LogLine(0, 0, "[BLE] clients=1")
        assertTrue(LogFilter.matches(l, ""))
        assertTrue(LogFilter.matches(l, "   "))
        assertTrue("关键字大小写不该影响", LogFilter.matches(l, "ble"))
        assertTrue(LogFilter.matches(l, "clients"))
        assertTrue("不匹配就得挡住", !LogFilter.matches(l, "ota"))
    }

    /** 暂停＝冻住那一屏；这期间来的行只计数，恢复后按原顺序补上。 */
    @Test
    fun pauseFreezesScreenAndCountsNewLines() {
        val lines = (1..5).map { LogLine(it.toLong(), 0, "line$it") }
        assertEquals(5, LogView.visible(lines, null, "").size)
        assertEquals(0, LogView.pending(lines, null))

        val paused = LogView.visible(lines, 3, "")
        assertEquals(listOf("line1", "line2", "line3"), paused.map { it.text })
        assertEquals(2, LogView.pending(lines, 3))

        // 恢复（pausedAt=null）后新行按原顺序出现在末尾
        assertEquals("line5", LogView.visible(lines, null, "").last().text)
    }

    /** 过滤只作用在暂停窗口内：窗口外的行不许因为关键字命中就冒出来。 */
    @Test
    fun filterStaysInsidePausedWindow() {
        val lines = (1..5).map { LogLine(it.toLong(), 0, "line$it") }
        assertEquals(listOf("line2"), LogView.visible(lines, 4, "2").map { it.text })
        assertEquals(1, LogView.pending(lines, 4))
    }

    @Test
    fun writesEveryLineToDisk() {
        val dir = tmp()
        val store = LogStore(dir)
        val f = store.start(ts(2026, 9, 22, 13, 4, 5, 0))
        store.append(LogLine(ts(2026, 9, 22, 13, 4, 5, 123), 0, "boot ok"))
        store.append(LogLine(ts(2026, 9, 22, 13, 4, 6, 0), 1, "[ble] clients=1"))
        store.close()

        assertEquals("log-20260922-130405.log", f.name)
        assertEquals(
            listOf(
                "2026-09-22 13:04:05.123 [I] boot ok",
                "2026-09-22 13:04:06.000 [W] [ble] clients=1",
            ),
            f.readLines(),
        )
    }

    /** 只留最近 5 个会话文件，第 6 个进来时最老的那个必须被删掉。 */
    @Test
    fun keepsOnlyTheNewestFiveSessions() {
        val dir = tmp()
        val store = LogStore(dir, keepFiles = 5)
        repeat(6) { i ->
            store.start(ts(2026, 9, 22, 13, 0, i, 0))
            store.append("session $i")
        }
        store.close()

        val names = store.files().map { it.name }
        assertEquals(5, names.size)
        assertTrue("最新的必须在", names.contains("log-20260922-130005.log"))
        assertTrue("最老的必须被清掉", !names.contains("log-20260922-130000.log"))
    }

    /** 没落盘时 append 不该崩（诊断页可能没开落盘）。 */
    @Test
    fun appendWithoutStartIsHarmless() {
        val store = LogStore(tmp())
        store.append("no file yet")
        assertEquals(null, store.current)
    }
}
