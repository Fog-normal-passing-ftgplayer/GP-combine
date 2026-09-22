package com.gpcombine.assistant.term

import com.gpcombine.assistant.proto.LogCodec
import com.gpcombine.assistant.proto.Proto

/** 终端要发的东西：要么是"套帧的协议命令"，要么是"原样吐出去的裸字节"。 */
sealed interface TermRequest {
    data class Command(val cmd: Int, val payload: ByteArray) : TermRequest
    data class Raw(val bytes: ByteArray) : TermRequest
}

sealed interface TermParse {
    /** 可以发。echo 是回显给人看的规范写法。 */
    data class Ok(val request: TermRequest, val echo: String) : TermParse
    /** 说清楚哪儿错了，别只回一句"语法错误"。 */
    data class Bad(val message: String) : TermParse
    /** 空行、或 help/HELP 这种本地命令。 */
    data class Local(val text: String) : TermParse
}

/**
 * 命令行解析。纯逻辑、不碰蓝牙，所以能在主机侧测。
 *
 * 约定：命令名大小写随意；十六进制允许空格、逗号、`0x` 前缀。
 * 直接贴一串 hex 等价于 `raw <hex>`——手头有串口日志想复现一帧时最省事。
 */
object Terminal {
    val HELP: List<String> = listOf(
        "ping                 探活（载荷原样回）",
        "info                 固件 / 分区 / 存储 / 内存",
        "pair                 配对码、蓝牙开关、已连手机数",
        "auth <6位配对码>      重新认证（会记到本机，下次自动用）",
        "logs on              开始推日志",
        "logs off             停止推日志",
        "logs replay <n>      开始推日志并回放最近 n 行（默认 40）",
        "cfg get              读 17 字节设置镜像（十六进制）",
        "cfg apply <34位hex>  只应用不落盘",
        "cfg set <34位hex>    应用并保存到设备",
        "cfg reset            恢复出厂默认",
        "raw <hex>            原样发裸字节（不套帧；回包会记成“无请求匹配”）",
        "<hex>                直接贴裸字节，等同 raw",
        "clear / cls          清屏",
    )

    fun parse(line: String): TermParse {
        val text = line.trim()
        if (text.isEmpty()) return TermParse.Local("")
        val parts = text.split(Regex("\\s+"))
        val cmd = parts[0].lowercase()

        return when (cmd) {
            "help", "?" -> TermParse.Local(HELP.joinToString("\n"))
            "clear", "cls" -> TermParse.Local("__clear__")
            "ping" -> ok(Proto.CMD_PING, Proto.EMPTY, "ping")
            "info" -> ok(Proto.CMD_INFO, Proto.EMPTY, "info")
            "pair" -> ok(Proto.CMD_PAIR_INFO, Proto.EMPTY, "pair")

            "auth" -> {
                val code = parts.getOrNull(1)
                    ?: return TermParse.Bad("auth 要带配对码，例如：auth 280148")
                if (code.length != 6) return TermParse.Bad("配对码是 6 位，收到 ${code.length} 位")
                ok(Proto.CMD_AUTH, code.toByteArray(Charsets.US_ASCII), "auth $code")
            }

            "logs", "log" -> parseLogs(parts)
            "cfg" -> parseCfg(parts)

            "raw", "hex" -> {
                val hex = parts.drop(1).joinToString("")
                if (hex.isEmpty()) return TermParse.Bad("raw 要带十六进制，例如：raw A5 5A")
                val bytes = parseHex(hex) ?: return TermParse.Bad("十六进制解不开：$hex")
                TermParse.Ok(TermRequest.Raw(bytes), "raw ${bytes.joinToString(" ") { "%02X".format(it) }}")
            }

            else -> {
                // 不是命令名就当成裸 hex 试试（粘贴串口日志里的一帧）
                val bytes = parseHex(text)
                if (bytes != null && bytes.isNotEmpty()) {
                    TermParse.Ok(TermRequest.Raw(bytes), "raw ${bytes.joinToString(" ") { "%02X".format(it) }}")
                } else {
                    TermParse.Bad("不认识的命令「$cmd」，打 help 看用法")
                }
            }
        }
    }

    private fun ok(cmd: Int, payload: ByteArray, echo: String) =
        TermParse.Ok(TermRequest.Command(cmd, payload), echo)

    private fun parseLogs(parts: List<String>): TermParse {
        if (parts.size < 2) return TermParse.Bad("logs 要跟参数：on / off / replay <n>")
        return when (parts[1].lowercase()) {
            "on" -> ok(
                Proto.CMD_LOG_SUB,
                LogCodec.subPayload(LogCodec.SUB_ON),
                "logs on",
            )
            "off" -> ok(
                Proto.CMD_LOG_SUB,
                LogCodec.subPayload(LogCodec.SUB_OFF),
                "logs off",
            )
            "replay" -> {
                val n = parts.getOrNull(2)?.toIntOrNull() ?: LogCodec.DEFAULT_REPLAY
                if (n <= 0) return TermParse.Bad("回放行数要大于 0")
                ok(
                    Proto.CMD_LOG_SUB,
                    LogCodec.subPayload(LogCodec.SUB_ON_REPLAY, n),
                    "logs replay $n",
                )
            }
            else -> TermParse.Bad("logs 只认 on / off / replay，收到「${parts[1]}」")
        }
    }

    private fun parseCfg(parts: List<String>): TermParse {
        val sub = parts.getOrNull(1)?.lowercase() ?: "get"
        return when (sub) {
            "get", "show" -> ok(Proto.CMD_CFG_GET, Proto.EMPTY, "cfg get")
            "reset" -> ok(Proto.CMD_CFG_RESET, Proto.EMPTY, "cfg reset")
            "apply", "set" -> {
                val hex = parts.drop(2).joinToString("")
                if (hex.isEmpty()) {
                    return TermParse.Bad("cfg $sub 要带 17 字节十六进制（34 位），例如：cfg $sub 01 01 ...")
                }
                val bytes = parseHex(hex) ?: return TermParse.Bad("十六进制解不开：$hex")
                if (bytes.size != 17) return TermParse.Bad("设置镜像是 17 字节，收到 ${bytes.size}")
                val cmd = if (sub == "apply") Proto.CMD_CFG_APPLY else Proto.CMD_CFG_SET
                ok(cmd, bytes, "cfg $sub ${bytes.joinToString(" ") { "%02X".format(it) }}")
            }
            else -> TermParse.Bad("cfg 只认 get / apply / set / reset，收到「$sub」")
        }
    }

    /** 允许 "A5 5A"、"a55a"、"0xA5,0x5A"；奇数位或非法字符返回 null。 */
    fun parseHex(s: String): ByteArray? {
        val cleaned = s.replace("0x", "", ignoreCase = true).replace(Regex("[\\s,，]"), "")
        if (cleaned.isEmpty()) return null
        if (cleaned.length % 2 != 0) return null
        if (!cleaned.all { it.isDigit() || it.lowercaseChar() in 'a'..'f' }) return null
        return ByteArray(cleaned.length / 2) { i ->
            cleaned.substring(i * 2, i * 2 + 2).toInt(16).toByte()
        }
    }
}
