package com.gpcombine.assistant.proto

/**
 * 配置档（设备里是 `/profiles/1.cfg`…`/profiles/5.cfg`）。
 *
 * 设备回的列表是 5 条**定长**记录（每 23 字节：[槽号][是否占用][名字长][名字 20 字节]），
 * 固件侧同一份布局在 `src/net/profiles.h`，两边测试用同一组规则。
 */
object Profiles {
    const val SLOTS = 5
    const val RECORD_BYTES = 23

    /** 名字上限 20 **字节**（中文一个字 3 字节，所以最多 6 个字）。 */
    const val NAME_MAX = 20

    data class Entry(val slot: Int, val used: Boolean, val name: String)

    fun parseList(b: ByteArray): List<Entry>? {
        if (b.size < SLOTS * RECORD_BYTES) return null
        return (0 until SLOTS).map { i ->
            val o = i * RECORD_BYTES
            val len = ((b[o + 2].toInt() and 0xFF)).coerceAtMost(NAME_MAX)
            Entry(
                slot = b[o].toInt() and 0xFF,
                used = (b[o + 1].toInt() and 0xFF) != 0,
                // 名字按长度取，不按 '\0' 截：设备写的是定长区，后面可能留着上次的残渣
                name = String(b, o + 3, len, Charsets.UTF_8),
            )
        }
    }

    /**
     * 去掉首尾空白与控制字符，并按**整字符**截到 20 字节。
     * 按字节硬切会把中文切成半个字符，设备上显示成方块 —— 宁可少一个字。
     */
    fun sanitizeName(raw: String): String {
        val trimmed = raw.trim().filter { it.code >= 0x20 && it.code != 0x7F }
        val sb = StringBuilder()
        var bytes = 0
        var i = 0
        while (i < trimmed.length) {
            val cp = trimmed.codePointAt(i)
            val s = String(Character.toChars(cp))
            val n = s.toByteArray(Charsets.UTF_8).size
            if (bytes + n > NAME_MAX) break
            sb.append(s)
            bytes += n
            i += Character.charCount(cp)
        }
        return sb.toString()
    }

    /** CMD_PROF_SAVE 的载荷：[槽号][名字长][名字]。空名字 = 用设备默认名。 */
    fun savePayload(slot: Int, name: String): ByteArray {
        val nb = sanitizeName(name).toByteArray(Charsets.UTF_8)
        val out = ByteArray(2 + nb.size)
        out[0] = slot.toByte()
        out[1] = nb.size.toByte()
        nb.copyInto(out, 2)
        return out
    }

    /** CMD_PROF_LOAD / CMD_PROF_DEL 的载荷（1 字节槽号）。非法槽位返回 null。 */
    fun slotPayload(slot: Int): ByteArray? =
        if (slot in 1..SLOTS) byteArrayOf(slot.toByte()) else null

    /** 界面上的显示名：没起名字的档显示"档N"。 */
    fun displayName(e: Entry): String = if (e.name.isEmpty()) "档${e.slot}" else e.name
}
