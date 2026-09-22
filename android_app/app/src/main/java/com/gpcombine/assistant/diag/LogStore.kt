package com.gpcombine.assistant.diag

import java.io.BufferedWriter
import java.io.File
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/** 设备推上来的一行日志 + 本机收到它的时间（设备端不带时间戳，只有重启后的相对时间）。 */
data class LogLine(val tsMs: Long, val level: Int, val text: String)

/** 屏幕上和文件里用同一套格式，免得"文件里一套、屏幕上另一套"对不上。 */
object LogFormat {
    private val SESSION = DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss")
    private val STAMP = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss.SSS")

    fun sessionName(nowMs: Long): String =
        SESSION.format(Instant.ofEpochMilli(nowMs).atZone(ZoneId.systemDefault()))

    fun stamp(tsMs: Long): String =
        STAMP.format(Instant.ofEpochMilli(tsMs).atZone(ZoneId.systemDefault()))

    /** 固件目前的调试输出没有等级体系，先按 0=普通 / 1=注意 / 2=错误 透传。 */
    fun tag(level: Int): String = when (level) {
        0 -> "I"
        1 -> "W"
        2 -> "E"
        else -> "?$level"
    }

    fun line(l: LogLine): String = "${stamp(l.tsMs)} [${tag(l.level)}] ${l.text}"
}

object LogFilter {
    /** 空关键字=全过；忽略大小写，随手搜 "ble" 也能命中 "[BLE]" 那一行。 */
    fun matches(l: LogLine, keyword: String): Boolean {
        val k = keyword.trim()
        return k.isEmpty() || l.text.contains(k, ignoreCase = true)
    }
}

/**
 * 日志页的显示算术：暂停时冻住当前那一屏，新来的只计数不插队。
 * 单独拎出来是因为 UI 里这几行索引最容易写错，而且主机侧能直接测。
 */
object LogView {
    fun visible(lines: List<LogLine>, pausedAt: Int?, keyword: String): List<LogLine> {
        val upto = (pausedAt ?: lines.size).coerceIn(0, lines.size)
        return lines.subList(0, upto).filter { LogFilter.matches(it, keyword) }
    }

    /** 暂停期间攒了多少行——没暂停就是 0。 */
    fun pending(lines: List<LogLine>, pausedAt: Int?): Int =
        if (pausedAt == null) 0 else (lines.size - pausedAt).coerceAtLeast(0)
}

/**
 * 日志落盘。一个会话一个文件，目录里只留最近 [keepFiles] 个，别把用户手机塞满。
 *
 * 用 java.io.File 而不是 Android 的 openFileOutput：纯 JVM 就能测，比开模拟器快得多。
 */
class LogStore(private val dir: File, private val keepFiles: Int = 5) {
    private var file: File? = null
    private var out: BufferedWriter? = null

    val current: File? get() = file

    /** 开一个会话文件；返回它的路径。 */
    fun start(nowMs: Long): File {
        close()
        if (!dir.exists()) dir.mkdirs()
        val f = File(dir, "log-${LogFormat.sessionName(nowMs)}.log")
        file = f
        out = f.bufferedWriter()
        prune()
        return f
    }

    fun append(line: String) {
        val w = out ?: return
        runCatching {
            w.append(line).append('\n')
            // 每行都刷：崩了/掉线了，最后几行也得留在文件里——那几行往往才是要看的
            w.flush()
        }
    }

    fun append(l: LogLine) = append(LogFormat.line(l))

    fun close() {
        runCatching { out?.close() }
        out = null
    }

    /** 现存会话文件，新的在前。 */
    fun files(): List<File> =
        dir.listFiles { f -> f.isFile && f.name.startsWith("log-") && f.name.endsWith(".log") }
            ?.sortedByDescending { it.name } ?: emptyList()

    private fun prune() {
        files().drop(keepFiles).forEach { runCatching { it.delete() } }
    }
}
