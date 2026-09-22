package com.gpcombine.assistant.term

import com.gpcombine.assistant.ble.BleTransport
import com.gpcombine.assistant.net.DeviceClient
import com.gpcombine.assistant.net.DeviceException
import com.gpcombine.assistant.net.Dir
import com.gpcombine.assistant.net.FrameRecord
import com.gpcombine.assistant.proto.ErrText
import com.gpcombine.assistant.proto.EspConfig
import com.gpcombine.assistant.proto.Frame
import com.gpcombine.assistant.proto.InfoCodec
import com.gpcombine.assistant.proto.LogCodec
import com.gpcombine.assistant.proto.Proto
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class TermLine(val tsMs: Long, val kind: Kind, val text: String) {
    enum class Kind { ECHO, INFO, ERR }
}

data class TermState(
    val lines: List<TermLine> = emptyList(),
    val busy: Boolean = false,
    /** 上一条命令（输入框的"重发"用）。 */
    val lastCommand: String = "",
)

/**
 * 终端页：把一行命令变成帧发出去，再把回包翻译成人看得懂的东西。
 *
 * 收发本身不在这里记流水：`DeviceClient.frames` 已经把每一帧（连"没人认领的回包"）
 * 都记下来了，终端只是把同一份流水渲染一遍 —— 这样"终端里看到的"和"帧监视器里看到的"
 * 永远是同一件事，不会出现两套记录各说各话。
 */
class TerminalController(
    private val client: DeviceClient,
    private val transport: BleTransport,
    private val scope: CoroutineScope,
    private val onPairCode: (String) -> Unit = {},
    private val clock: () -> Long = { System.currentTimeMillis() },
) {
    private val _state = MutableStateFlow(TermState())
    val state: StateFlow<TermState> = _state.asStateFlow()

    init {
        // 帧流水直接进终端：发出去的、收回来的、设备主动推的，都在这一条时间线上
        scope.launch {
            client.frames.collect { r -> append(FrameLine(kind = TermLine.Kind.INFO, record = r)) }
        }
    }

    fun send(line: String) {
        when (val p = Terminal.parse(line)) {
            is TermParse.Bad -> append(TermLine.Kind.ERR, p.message)
            is TermParse.Local -> {
                if (p.text == "__clear__") clear() else if (p.text.isNotEmpty()) append(p.text)
            }
            is TermParse.Ok -> {
                append(TermLine.Kind.ECHO, p.echo)
                _state.update { it.copy(busy = true, lastCommand = line.trim()) }
                scope.launch {
                    try {
                        when (val r = p.request) {
                            is TermRequest.Raw -> {
                                // 裸字节不套帧、不占 seq：回包会以"无请求匹配"落在帧流里
                                transport.send(r.bytes)
                                append("已原样发出 ${r.bytes.size} 字节（不套帧，回包不会和它配对）")
                            }
                            is TermRequest.Command -> {
                                val reply = client.sendRequest(r.cmd, r.payload)
                                if (r.cmd == Proto.CMD_AUTH && reply.payload.isNotEmpty() &&
                                    reply.payload[0].toInt() == 1
                                ) {
                                    val code = String(r.payload, Charsets.US_ASCII)
                                    onPairCode(code)
                                    append("认证通过，配对码已记住")
                                }
                                describe(reply)?.let { append(it) }
                            }
                        }
                    } catch (e: DeviceException) {
                        append(TermLine.Kind.ERR, "错误 0x%02X：%s%s".format(
                            e.code, ErrText.of(e.code), if (e.message.isNullOrEmpty()) "" else "（${e.message}）",
                        ))
                    } catch (e: Exception) {
                        append(TermLine.Kind.ERR, "没发出去/没等到回包：${e.message}")
                    } finally {
                        _state.update { it.copy(busy = false) }
                    }
                }
            }
        }
    }

    fun clear() = _state.update { it.copy(lines = emptyList()) }

    /** 回包翻译成人话；不需要翻译的命令返回 null（原始帧流水已经显示了）。 */
    private fun describe(f: Frame): String? = when (f.cmd) {
        Proto.CMD_PING -> if (f.payload.isEmpty()) "pong（空载荷）"
        else "pong，回显 ${f.payload.size} 字节"

        Proto.CMD_AUTH -> "认证${if (f.payload.isNotEmpty() && f.payload[0].toInt() == 1) "通过" else "失败"}"

        Proto.CMD_INFO -> runCatching {
            val i = InfoCodec.parseInfo(String(f.payload, Charsets.US_ASCII))
            "固件 ${i.version}，固件 ${i.appBytes} B，卡 ${i.fsUsed}/${i.fsTotal}，" +
                "内部 RAM 余 ${i.ramFree}，PSRAM 余 ${i.psramFree}"
        }.getOrElse { "INFO 解析不了：${String(f.payload, Charsets.US_ASCII)}" }

        Proto.CMD_PAIR_INFO -> String(f.payload, Charsets.US_ASCII)

        Proto.CMD_LOG_SUB -> if (f.payload.isNotEmpty() && f.payload[0].toInt() != 0)
            "日志推送已开（回放的行马上会出现在下面）" else "日志推送已关"

        Proto.CMD_CFG_GET -> EspConfig.fromBytes(f.payload)?.let { cfg ->
            "主题=${EspConfig.THEME_NAMES[cfg.theme]} 风格=${EspConfig.STYLE_NAMES[cfg.style]} " +
                "透明度=${EspConfig.OPACITY_NAMES[cfg.bgOpacity]} 背光=${cfg.backlight} " +
                "翻转=${cfg.flipX}/${cfg.flipY} 反色=${cfg.invert} " +
                "屏保=${EspConfig.SAVER_NAMES[cfg.saverMode]}/${cfg.saverSecs}s 关屏=${cfg.screenOff} " +
                "输入历史=${cfg.inputHistory} 布局=${EspConfig.LAYOUT_NAMES[cfg.layout]} 无线=${cfg.wireless}"
        } ?: "设置镜像读不出来（版本/长度不对）"

        Proto.CMD_CFG_APPLY, Proto.CMD_CFG_SET -> "设备已应用" +
            if (f.cmd == Proto.CMD_CFG_SET) "并保存（断电重启仍生效）" else "（未写 flash）"

        Proto.CMD_CFG_RESET -> "已恢复出厂默认"
        else -> null
    }

    private fun FrameLine(kind: TermLine.Kind, record: FrameRecord): TermLine {
        val arrow = if (record.dir == Dir.TX) "→" else "←"
        val note = if (record.note.isEmpty()) "" else "  [${record.note}]"
        val body = record.text.takeIf { it.isNotEmpty() && it.all { c -> c.code in 32..126 } }
        val shown = when {
            record.hex.isEmpty() -> "(无载荷)"
            body != null -> "${record.hex}  \"$body\""
            else -> record.hex
        }
        return TermLine(
            tsMs = record.timeMs,
            kind = TermLine.Kind.INFO,
            text = "$arrow ${FrameRecord.cmdName(record.cmd)} seq=${record.seq} ${record.len}B  $shown$note",
        )
    }

    private fun append(text: String) = append(TermLine.Kind.INFO, text)

    private fun append(kind: TermLine.Kind, text: String) =
        append(TermLine(kind = kind, tsMs = clock(), text = text))

    private fun append(line: TermLine) {
        _state.update { it.copy(lines = (it.lines + line).takeLast(MAX_LINES)) }
    }

    companion object {
        const val MAX_LINES = 400
    }
}
