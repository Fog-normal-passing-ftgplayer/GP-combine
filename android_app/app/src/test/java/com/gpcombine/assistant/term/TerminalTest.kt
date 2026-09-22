package com.gpcombine.assistant.term

import com.gpcombine.assistant.ble.FakeTransport
import com.gpcombine.assistant.net.DeviceClient
import com.gpcombine.assistant.proto.LogCodec
import com.gpcombine.assistant.proto.Proto
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class TerminalTest {
    private fun command(line: String): TermRequest.Command =
        (Terminal.parse(line) as TermParse.Ok).request as TermRequest.Command

    private fun bad(line: String): String = (Terminal.parse(line) as TermParse.Bad).message

    @Test
    fun plainCommandsMapToProtocolCommands() {
        assertEquals(Proto.CMD_PING, command("ping").cmd)
        assertEquals(Proto.CMD_INFO, command("  INFO  ").cmd)   // 大小写/空格都随意
        assertEquals(Proto.CMD_PAIR_INFO, command("pair").cmd)
        assertTrue(command("ping").payload.isEmpty())
    }

    @Test
    fun authNeedsSixCharacters() {
        val c = command("auth 280148")
        assertEquals(Proto.CMD_AUTH, c.cmd)
        assertEquals("280148", String(c.payload, Charsets.US_ASCII))
        assertTrue(bad("auth 123").contains("6 位"))
        assertTrue(bad("auth").contains("配对码"))
    }

    /** 载荷字节必须和固件 protoParseLogSub 对得上：mode 必须在第 0 位。 */
    @Test
    fun logsPayloadMatchesFirmwareLayout() {
        val on = command("logs on")
        assertEquals(Proto.CMD_LOG_SUB, on.cmd)
        assertEquals(LogCodec.SUB_ON, on.payload[0].toInt())
        assertEquals(1, on.payload.size)

        val off = command("logs off")
        assertEquals(LogCodec.SUB_OFF, off.payload[0].toInt())

        val replay = command("logs replay 8")
        assertEquals(LogCodec.SUB_ON_REPLAY, replay.payload[0].toInt())
        assertEquals(8, replay.payload[1].toInt())

        val dflt = command("logs replay")
        assertEquals(LogCodec.DEFAULT_REPLAY, dflt.payload[1].toInt())

        assertTrue(bad("logs replay 0").contains("大于 0"))
        assertTrue(bad("logs wow").contains("on / off / replay"))
        assertTrue(bad("logs").contains("on / off / replay"))
    }

    @Test
    fun cfgCommandsCheckTheSeventeenByteMirror() {
        assertEquals(Proto.CMD_CFG_GET, command("cfg get").cmd)
        assertEquals(Proto.CMD_CFG_GET, command("cfg").cmd)
        assertEquals(Proto.CMD_CFG_RESET, command("cfg reset").cmd)

        val hex = (1..17).joinToString(" ") { "%02X".format(it) }
        val apply = command("cfg apply $hex")
        assertEquals(Proto.CMD_CFG_APPLY, apply.cmd)
        assertEquals(17, apply.payload.size)
        assertEquals(0x01, apply.payload[0].toInt())
        assertEquals(0x11, apply.payload[16].toInt())

        val set = command("cfg set $hex")
        assertEquals(Proto.CMD_CFG_SET, set.cmd)

        assertTrue(bad("cfg set 01 02 03").contains("17 字节"))
        assertTrue(bad("cfg set").contains("34 位"))
        assertTrue(bad("cfg frobnicate").contains("get / apply / set / reset"))
    }

    @Test
    fun hexParsingIsForgivingButNotSloppy() {
        val want = byteArrayOf(0xA5.toByte(), 0x5A, 0x01)
        assertEquals(want.toList(), Terminal.parseHex("A5 5A 01")!!.toList())
        assertEquals(want.toList(), Terminal.parseHex("a55a01")!!.toList())
        assertEquals(want.toList(), Terminal.parseHex("0xA5,0x5A,0x01")!!.toList())
        assertNull("奇数位不是字节流", Terminal.parseHex("A55"))
        assertNull("非十六进制", Terminal.parseHex("ZZ"))
        assertNull("空串", Terminal.parseHex("   "))
    }

    /** 直接贴一串 hex 等价于 raw：从串口日志里复现一帧时最省事。 */
    @Test
    fun bareHexIsTreatedAsRaw() {
        val p = Terminal.parse("A5 5A 01") as TermParse.Ok
        val r = p.request as TermRequest.Raw
        assertEquals(3, r.bytes.size)
        assertEquals(0xA5, r.bytes[0].toInt() and 0xFF)
        assertTrue(p.echo.startsWith("raw "))

        val raw = (Terminal.parse("raw a55a") as TermParse.Ok).request as TermRequest.Raw
        assertEquals(2, raw.bytes.size)
    }

    @Test
    fun unknownAndLocalCommands() {
        assertTrue(bad("frobnicate").contains("help"))
        val help = Terminal.parse("help") as TermParse.Local
        assertTrue(help.text.contains("cfg apply"))
        assertEquals("__clear__", (Terminal.parse("clear") as TermParse.Local).text)
        assertEquals("", (Terminal.parse("   ") as TermParse.Local).text)
    }

    // ---- 控制器：真跑一遍假设备 ----

    @Test
    fun pingShowsRequestReplyAndPongInOneTimeline() = runTest {
        val t = FakeTransport().apply { connect() }
        val c = DeviceClient(t, backgroundScope)
        val term = TerminalController(c, t, backgroundScope)

        term.send("ping")
        runCurrent()
        runCurrent()

        val texts = term.state.value.lines.map { it.text }
        assertTrue("要有命令回显：$texts", texts.any { it == "ping" })
        assertTrue("要有发帧记录：$texts", texts.any { it.startsWith("→ PING") })
        assertTrue("要有回包记录：$texts", texts.any { it.startsWith("← PING") })
        assertTrue("要有 pong 摘要：$texts", texts.any { it.contains("pong") })
        assertEquals(false, term.state.value.busy)
    }

    /** 设备回错误帧要变成人话，而不是一串异常栈。 */
    @Test
    fun deviceErrorBecomesReadableLine() = runTest {
        val t = FakeTransport().apply { connect() }   // 没认证
        val c = DeviceClient(t, backgroundScope)
        val term = TerminalController(c, t, backgroundScope)

        term.send("info")
        runCurrent()
        runCurrent()

        val texts = term.state.value.lines.map { it.text }
        assertTrue("要报错误码和人话：$texts", texts.any { it.startsWith("错误 0x04") && it.contains("配对码") })
    }

    /** cfg get 要把 17 字节翻译成设备菜单里那套名字，别让人去数十六进制。 */
    @Test
    fun cfgGetIsTranslatedToNames() = runTest {
        val t = FakeTransport().apply { connect() }
        val c = DeviceClient(t, backgroundScope)
        c.auth("280148")
        val term = TerminalController(c, t, backgroundScope)

        term.send("cfg get")
        runCurrent()
        runCurrent()

        val texts = term.state.value.lines.map { it.text }
        assertTrue("要有人话摘要：$texts", texts.any { it.startsWith("主题=") && it.contains("布局=") })
    }

    /** 裸字节不套帧：控制器要如实说出来，别让用户以为它会和回包配对。 */
    @Test
    fun rawBytesAreSentUnframedAndSaidSo() = runTest {
        val t = FakeTransport().apply { connect() }
        val c = DeviceClient(t, backgroundScope)
        val term = TerminalController(c, t, backgroundScope)

        term.send("raw A5 5A")
        runCurrent()
        runCurrent()

        val texts = term.state.value.lines.map { it.text }
        assertTrue("要说明没套帧：$texts", texts.any { it.contains("原样发出 2 字节") })
        assertTrue("不该有套帧的请求记录", t.sent().none { it.cmd == Proto.CMD_PING })
    }

    @Test
    fun clearEmptiesTheScreen() = runTest {
        val t = FakeTransport().apply { connect() }
        val c = DeviceClient(t, backgroundScope)
        val term = TerminalController(c, t, backgroundScope)
        term.send("ping")
        runCurrent()
        runCurrent()
        assertTrue(term.state.value.lines.isNotEmpty())

        term.clear()

        assertTrue(term.state.value.lines.isEmpty())
    }
}
