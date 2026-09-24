package com.gpcombine.assistant.proto

data class DeviceInfo(
    val version: String,
    val appBytes: Long,
    val fsTotal: Long,
    val fsUsed: Long,
    val ramFree: Long,
    val psramFree: Long,
)

data class PairInfo(
    val name: String,
    val pairCode: String,
    val btEnabled: Boolean,
    val clients: Int,
    val apEnabled: Boolean,
)

/**
 * 解析固件回的键值串。缺字段直接抛异常而不是悄悄给 0——
 * 悄悄给 0 会变成界面上一个看起来正常的"0 字节"，比报错难查得多。
 *
 * 注意切分顺序：先 ';' 切字段、再 '=' 切键值，最后才轮到 'fs' 的值按 '/' 切两半。
 */
object InfoCodec {
    private fun fields(s: String): Map<String, String> =
        s.split(';').mapNotNull { part ->
            val i = part.indexOf('=')
            if (i <= 0) null else part.substring(0, i) to part.substring(i + 1)
        }.toMap()

    private fun Map<String, String>.need(key: String): String =
        this[key] ?: throw IllegalArgumentException("回包里没有字段 `$key`，收到的是：$this")

    private fun Map<String, String>.num(key: String): Long =
        need(key).toLongOrNull() ?: throw IllegalArgumentException("字段 `$key` 不是数字：${this[key]}")

    fun parseInfo(s: String): DeviceInfo {
        val f = fields(s)
        val fs = f.need("fs").split('/')
        require(fs.size == 2) { "fs 字段不是 总量/已用 两段：${f["fs"]}" }
        return DeviceInfo(
            version = f.need("ver"),
            appBytes = f.num("app"),
            fsTotal = fs[0].toLongOrNull() ?: throw IllegalArgumentException("fs 总量不是数字：${fs[0]}"),
            fsUsed = fs[1].toLongOrNull() ?: throw IllegalArgumentException("fs 已用不是数字：${fs[1]}"),
            ramFree = f.num("ram"),
            psramFree = f.num("psram"),
        )
    }

    fun parsePairInfo(s: String): PairInfo {
        val f = fields(s)
        return PairInfo(
            name = f.need("name"),
            pairCode = f.need("pair"),
            btEnabled = f.num("bt") != 0L,
            clients = f.num("clients").toInt(),
            apEnabled = f.num("ap") != 0L,
        )
    }
}
