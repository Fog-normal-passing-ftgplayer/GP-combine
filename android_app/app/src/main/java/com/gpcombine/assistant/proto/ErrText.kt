package com.gpcombine.assistant.proto

/** 错误码 → 人话。散落在各处的字符串迟早会互相矛盾，集中一处。 */
object ErrText {
    const val ERR_OK = 0x00
    const val ERR_BAD_CRC = 0x01
    const val ERR_BAD_LEN = 0x02
    const val ERR_UNKNOWN_CMD = 0x03
    const val ERR_NOT_AUTHED = 0x04
    const val ERR_BAD_ARG = 0x05
    const val ERR_NO_MEM = 0x06
    const val ERR_IO = 0x07

    fun of(code: Int): String = when (code) {
        ERR_OK -> "成功"
        ERR_BAD_CRC -> "校验不过（帧被截断或串了）"
        ERR_BAD_LEN -> "载荷长度不对"
        ERR_UNKNOWN_CMD -> "设备不认这条命令"
        ERR_NOT_AUTHED -> "还没认证：先输配对码"
        ERR_BAD_ARG -> "参数不合法"
        ERR_NO_MEM -> "设备内存不够（日志队列申请失败）"
        ERR_IO -> "设备存储读写失败（文件不存在 / 写不进去）"
        else -> "未知错误码 0x%02X".format(code)
    }
}
