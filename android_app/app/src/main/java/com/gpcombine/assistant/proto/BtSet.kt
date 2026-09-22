package com.gpcombine.assistant.proto

/**
 * CMD_BT_SET 的载荷构造：改设备名 / 改配对码 / 蓝牙开关。
 *
 *   0      flags bit0 名字 / bit1 配对码 / bit2 开关
 *   1      开关值 0/1
 *   2      名字长度
 *   3..    名字（UTF-8）
 *   之后   配对码长度 + 配对码（6 位 ASCII 数字）
 *
 * 固件侧解析在 `src/net/proto.h::protoParseBtSet`，任何一处对不上整帧拒绝 ——
 * 这里在发之前就先挡一道，省得发出去只收到一句"参数错"。
 */
object BtSet {
    const val FLAG_NAME = 0x01
    const val FLAG_PAIR = 0x02
    const val FLAG_SW = 0x04

    /** 和固件 BT_NAME_MAX 一致。 */
    const val NAME_MAX = 20

    fun pairCodeValid(code: String): Boolean =
        code.length == 6 && code.all { it in '0'..'9' }

    /**
     * 传 null = 这一项不改。三项都是 null、或名字/配对码不合法时返回 null：
     * 发一帧"什么都没改"的空命令，只会得到一个看起来成功的回包，比报错更难查。
     */
    fun payload(name: String? = null, pairCode: String? = null, btOn: Boolean? = null): ByteArray? {
        var flags = 0
        if (name != null) flags = flags or FLAG_NAME
        if (pairCode != null) flags = flags or FLAG_PAIR
        if (btOn != null) flags = flags or FLAG_SW
        if (flags == 0) return null

        val nb = (name ?: "").toByteArray(Charsets.UTF_8)
        if (name != null && (nb.isEmpty() || nb.size > NAME_MAX)) return null
        if (pairCode != null && !pairCodeValid(pairCode)) return null
        val pb = (pairCode ?: "").toByteArray(Charsets.US_ASCII)
        if (pb.size > 127) return null

        val out = ByteArray(3 + nb.size + 1 + pb.size)
        out[0] = flags.toByte()
        out[1] = (if (btOn == true) 1 else 0).toByte()
        out[2] = nb.size.toByte()
        nb.copyInto(out, 3)
        out[3 + nb.size] = pb.size.toByte()
        pb.copyInto(out, 4 + nb.size)
        return out
    }
}
