# GP-Combine 手机 App（M1 控制面）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 手机上装一个 APK，能扫描到 `GP-Combine-XXXX`、连接、输入屏幕上那 6 位配对码通过 AUTH，然后在设备页看到固件 INFO（版本 / 分区 / 内存 / LittleFS 余量）。

**Architecture:** 协议核（CRC、组帧、增量收帧器、键值解析）是**纯 Kotlin**，不 import `android.*`，因此能在没有蓝牙适配器的本机跑 JVM 单测，并且**与固件 `tools/host_tests` 用同一组字节向量**。BLE 收发藏在 `BleTransport` 接口后，真机实现与 UI 解耦；`FakeTransport` 让 UI 在没有板子时也能跑通。固件侧协议已真机验证（见 spec §10），App 只是把同样的字节封进 GATT 写。

**Tech Stack:** Kotlin 2.4.20（AGP 9 内置，不加 kotlin.android 插件）、Jetpack Compose BOM 2026.09.00、AGP 9.4.1、Gradle 9.7.1、JDK 21、compileSdk 37 / minSdk 29 / targetSdk 34。

**Spec:** `docs/superpowers/specs/2026-09-18-phone-app-design.md`（§8 是 App 设计，§5 是协议）

## Global Constraints

- 包名 `com.gpcombine.assistant`；应用名 `GP-Combine`；界面中文。
- 目录 `android/`，单 Gradle module `:app`。所有路径都相对于仓库根。
- `compileSdk = 37`、`minSdk = 29`、`targetSdk = 34`。
- **不要加 `org.jetbrains.kotlin.android` 插件**：AGP 9 自带 Kotlin 支持，加了直接构建失败（报 "no longer required since AGP 9.0"）。
- `android/gradle.properties` 必须含 `org.gradle.java.home=/home/bit/.jdks/temurin-21`，否则 Gradle 用系统 JDK 26 起 daemon，AGP 起不来。
- 构建命令固定为：`cd android && /home/bit/tools/gradle-9.7.1/bin/gradle <task>`。**这些命令必须在沙箱外执行**（要写 `~/.gradle` 和 `~/Android/Sdk`）。
- `local.properties` 不进 git（内含本机 SDK 绝对路径）。
- 依赖只用 androidx / Compose / JUnit；**不引第三方库**（HTTP 那步以后用 `HttpURLConnection`）。
- 协议常数与字节布局必须与固件 `esp32_170x320/src/net/proto.h` 逐字一致，改一边必须改另一边。
- 提交信息用中文，写清"为什么"，不写"改了什么"。

---

## 文件结构

先定死每个文件负责什么，任务分解就跟着这个走。

| 文件 | 职责 |
|---|---|
| `android/settings.gradle.kts` | 工程名、包含 `:app`、仓库源 |
| `android/build.gradle.kts` | 根插件声明（AGP + Compose 编译器插件） |
| `android/gradle.properties` | JVM 参数、`org.gradle.java.home`、`android.useAndroidX` |
| `android/local.properties` | `sdk.dir`（不进 git） |
| `android/.gitignore` | 构建产物、`.gradle`、`local.properties` |
| `android/app/build.gradle.kts` | `:app` 的 android 配置与依赖 |
| `app/src/main/AndroidManifest.xml` | 权限声明、BLE feature、Activity |
| `app/src/main/res/values/themes.xml` | 无 ActionBar 主题（不引 appcompat） |
| `.../proto/Proto.kt` | 帧常数、`crc16`、`build`、`notifyChunk`（纯 Kotlin） |
| `.../proto/FrameParser.kt` | 增量收帧器，坏字节靠魔数重新同步（纯 Kotlin） |
| `.../proto/InfoCodec.kt` | `INFO` / `PAIR_INFO` 的键值串解析（纯 Kotlin） |
| `.../ble/BleTransport.kt` | BLE 抽象接口 + `BleState` |
| `.../ble/FakeTransport.kt` | 内置假设备，没板子时跑 UI |
| `.../ble/AndroidBleTransport.kt` | 真机 BLE：扫描/连接/MTU/订阅/写 |
| `.../net/DeviceClient.kt` | 会话层：seq 配对的请求-响应、超时、错误帧 |
| `.../store/Prefs.kt` | 上次设备地址、配对码 |
| `.../ui/MainActivity.kt` | 唯一 Activity、权限申请、页面切换 |
| `.../ui/DeviceViewModel.kt` | 持有 transport，对 UI 只暴露 `StateFlow` |
| `.../ui/ConnectScreen.kt` | 扫描列表 + 连接 + 输配对码 |
| `.../ui/DeviceScreen.kt` | INFO / PAIR_INFO 展示 |
| `.../ui/Theme.kt` | 深色主题 |
| `app/src/test/.../ProtoTest.kt` | 帧常数、CRC、组帧、分片（对齐固件向量） |
| `app/src/test/.../FrameParserTest.kt` | 收帧器：分片重组、坏 CRC、垃圾重同步 |
| `app/src/test/.../InfoCodecTest.kt` | 键值解析 |
| `app/src/test/.../DeviceClientTest.kt` | 请求-响应、超时、错误帧（用 FakeTransport） |

---

## Task 1: 工程骨架，能出 APK

**Files:**
- Create: `android/settings.gradle.kts`
- Create: `android/build.gradle.kts`
- Create: `android/gradle.properties`
- Create: `android/local.properties`
- Create: `android/.gitignore`
- Create: `android/app/build.gradle.kts`
- Create: `android/app/src/main/AndroidManifest.xml`
- Create: `android/app/src/main/res/values/themes.xml`
- Create: `android/app/src/main/java/com/gpcombine/assistant/ui/MainActivity.kt`

**Interfaces:**
- Consumes: 无
- Produces: 可构建的 `:app` 工程；包名 `com.gpcombine.assistant`；后续所有任务的落点

- [ ] **Step 1: 建工程文件**

`android/settings.gradle.kts`

```kotlin
pluginManagement {
    repositories { google(); mavenCentral(); gradlePluginPortal() }
}
dependencyResolutionManagement {
    repositories { google(); mavenCentral() }
}
rootProject.name = "gpcombine"
include(":app")
```

`android/build.gradle.kts`

```kotlin
plugins {
    id("com.android.application") version "9.4.1" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.4.20" apply false
}
```

`android/gradle.properties`

```properties
org.gradle.jvmargs=-Xmx2g -Dfile.encoding=UTF-8
org.gradle.java.home=/home/bit/.jdks/temurin-21
android.useAndroidX=true
```

`android/local.properties`（不进 git）

```properties
sdk.dir=/home/bit/Android/Sdk
```

`android/.gitignore`

```gitignore
.gradle/
build/
local.properties
*.iml
.idea/
```

`android/app/build.gradle.kts`

```kotlin
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "com.gpcombine.assistant"
    compileSdk = 37

    defaultConfig {
        applicationId = "com.gpcombine.assistant"
        minSdk = 29
        targetSdk = 34
        versionCode = 1
        versionName = "0.1"
    }

    buildFeatures { compose = true }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2026.09.00"))
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.11.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.11.0")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.11.0")
    implementation("androidx.core:core-ktx:1.19.0")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.11.0")
}
```

`android/app/src/main/AndroidManifest.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

    <uses-feature android:name="android.hardware.bluetooth_le" android:required="true" />

    <!-- API 31+ 的运行时权限 -->
    <uses-permission android:name="android.permission.BLUETOOTH_SCAN" />
    <uses-permission android:name="android.permission.BLUETOOTH_CONNECT" />
    <!-- API 30 及以下扫 BLE 必需 -->
    <uses-permission android:name="android.permission.BLUETOOTH" android:maxSdkVersion="30" />
    <uses-permission android:name="android.permission.BLUETOOTH_ADMIN" android:maxSdkVersion="30" />
    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
    <!-- P2 的 HTTP 数据面 -->
    <uses-permission android:name="android.permission.INTERNET" />

    <application
        android:label="GP-Combine"
        android:theme="@style/Theme.GPCombine">
        <activity
            android:name=".ui.MainActivity"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
```

`android/app/src/main/res/values/themes.xml`（用系统 Material 主题，不引 appcompat）

```xml
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <style name="Theme.GPCombine" parent="android:Theme.Material.NoActionBar" />
</resources>
```

`android/app/src/main/java/com/gpcombine/assistant/ui/MainActivity.kt`

```kotlin
package com.gpcombine.assistant.ui

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.material3.Text

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { Text("GP-Combine") }
    }
}
```

- [ ] **Step 2: 构建，确认出 APK**

Run: `cd android && /home/bit/tools/gradle-9.7.1/bin/gradle assembleDebug`
Expected: `BUILD SUCCESSFUL`，且 `android/app/build/outputs/apk/debug/app-debug.apk` 存在。

如果报 "kotlin.android plugin is no longer required"，说明 `app/build.gradle.kts` 里多写了那个插件，删掉。
如果报某个依赖要求更高 compileSdk，把 `compileSdk` 提到报错里要求的版本。

- [ ] **Step 3: 提交**

```bash
git add android/
git commit -m "feat(android): 建 GP-Combine App 工程骨架

单 module + Compose，compileSdk 37（Compose BOM 2026.09.00 的硬要求）。
AGP 9 自带 Kotlin 支持，所以只声明 com.android.application 和 Compose
编译器插件，不加 kotlin.android。gradle.properties 把 daemon 钉到 JDK 21，
否则 Gradle 会拿系统的 JDK 26 起 daemon，AGP 起不来。"
```

---

## Task 2: 协议核 —— 常数、CRC、组帧

**Files:**
- Create: `android/app/src/main/java/com/gpcombine/assistant/proto/Proto.kt`
- Test: `android/app/src/test/java/com/gpcombine/assistant/proto/ProtoTest.kt`

**Interfaces:**
- Consumes: 无
- Produces:
  - `Proto.MAGIC0/MAGIC1/VERSION/HEADER/MAX_PAYLOAD: Int`
  - `Proto.CMD_PING/CMD_AUTH/CMD_INFO/CMD_PAIR_INFO/CMD_CFG_GET/CMD_CFG_SET/CMD_CFG_RESET/CMD_ERR: Int`
  - `Proto.ERR_OK/ERR_BAD_CRC/ERR_BAD_LEN/ERR_UNKNOWN_CMD/ERR_NOT_AUTHED: Int`
  - `Proto.crc16(data: ByteArray, from: Int = 0, until: Int = data.size): Int`
  - `Proto.build(cmd: Int, seq: Int, payload: ByteArray = Proto.EMPTY): ByteArray`
  - `Proto.notifyChunk(mtu: Int, remaining: Int): Int`

**测试向量的来源**：下面每一个字节串都是今天真机串口日志里设备自己打出来的 `[ble] WR->frame`，不是手算的。固件的 `tools/host_tests/fixes_test.cpp` 也断言了同一批 CRC。App 侧跑通这组 = 两边协议一致。

- [ ] **Step 1: 写失败的测试**

`ProtoTest.kt`

```kotlin
package com.gpcombine.assistant.proto

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Test

class ProtoTest {
    private fun hex(s: String) = s.trim().split(" ").map { it.toInt(16).toByte() }.toByteArray()

    @Test
    fun crcMatchesFirmware() {
        assertEquals("PING 帧的 CRC", 0xE1E1, Proto.crc16(hex("01 01 00 00 00 00")))
        assertEquals(
            "AUTH(seq=0) 帧的 CRC",
            0xAD8D,
            Proto.crc16(hex("01 02 00 00 06 00 32 38 30 31 34 38")),
        )
    }

    @Test
    fun buildMatchesDeviceLog() {
        assertArrayEquals(
            hex("A5 5A 01 01 00 00 00 00 E1 E1"),
            Proto.build(Proto.CMD_PING, 0),
        )
        assertArrayEquals(
            hex("A5 5A 01 02 01 00 06 00 32 38 30 31 34 38 C8 C2"),
            Proto.build(Proto.CMD_AUTH, 1, "280148".toByteArray()),
        )
        assertArrayEquals(hex("A5 5A 01 03 02 00 00 00 0A 48"), Proto.build(Proto.CMD_INFO, 2))
        assertArrayEquals(hex("A5 5A 01 04 03 00 00 00 6A 59"), Proto.build(Proto.CMD_PAIR_INFO, 3))
        assertArrayEquals(hex("A5 5A 01 10 04 00 00 00 1B 85"), Proto.build(Proto.CMD_CFG_GET, 4))
    }

    @Test
    fun notifyChunkMatchesFirmware() {
        assertEquals(244, Proto.notifyChunk(247, 250))
        assertEquals(20, Proto.notifyChunk(23, 250))
        assertEquals(182, Proto.notifyChunk(185, 250))
        assertEquals(10, Proto.notifyChunk(247, 10))
        assertEquals(10, Proto.notifyChunk(0, 10))
        assertEquals(20, Proto.notifyChunk(0, 250))
    }

    @Test
    fun seqIsLittleEndian() {
        assertEquals(0x34, Proto.build(Proto.CMD_PING, 0x1234)[4].toInt() and 0xFF)
        assertEquals(0x12, Proto.build(Proto.CMD_PING, 0x1234)[5].toInt() and 0xFF)
    }
}
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `cd android && /home/bit/tools/gradle-9.7.1/bin/gradle :app:testDebugUnitTest`
Expected: 编译失败，`unresolved reference: Proto`。

- [ ] **Step 3: 实现 Proto.kt**

```kotlin
package com.gpcombine.assistant.proto

/**
 * 帧格式，与固件 esp32_170x320/src/net/proto.h 逐字对应，改一边必须改另一边。
 *
 *   A5 5A | ver=1 | cmd | seq(LE) | len(LE) | payload | CRC16-CCITT(LE，覆盖 ver..payload)
 */
object Proto {
    const val MAGIC0 = 0xA5
    const val MAGIC1 = 0x5A
    const val VERSION = 1
    const val HEADER = 8
    const val MAX_PAYLOAD = 256

    /** BLE 单次 notify/写 的 ATT 头占 3 字节 */
    private const val ATT_HEADER = 3

    const val CMD_PING = 0x01
    const val CMD_AUTH = 0x02
    const val CMD_INFO = 0x03
    const val CMD_PAIR_INFO = 0x04
    const val CMD_CFG_GET = 0x10
    const val CMD_CFG_SET = 0x11
    const val CMD_CFG_RESET = 0x12
    const val CMD_ERR = 0x7F

    const val ERR_OK = 0x00
    const val ERR_BAD_CRC = 0x01
    const val ERR_BAD_LEN = 0x02
    const val ERR_UNKNOWN_CMD = 0x03
    const val ERR_NOT_AUTHED = 0x04

    val EMPTY = ByteArray(0)

    /** CRC16-CCITT：初值 0xFFFF、多项式 0x1021、不反转 */
    fun crc16(data: ByteArray, from: Int = 0, until: Int = data.size): Int {
        var crc = 0xFFFF
        for (i in from until until) {
            crc = crc xor ((data[i].toInt() and 0xFF) shl 8)
            repeat(8) {
                crc = if (crc and 0x8000 != 0) ((crc shl 1) xor 0x1021) else (crc shl 1)
                crc = crc and 0xFFFF
            }
        }
        return crc
    }

    fun build(cmd: Int, seq: Int, payload: ByteArray = EMPTY): ByteArray {
        require(payload.size <= MAX_PAYLOAD) { "载荷 ${payload.size} 字节，超过 $MAX_PAYLOAD" }
        val out = ByteArray(HEADER + payload.size + 2)
        out[0] = MAGIC0.toByte()
        out[1] = MAGIC1.toByte()
        out[2] = VERSION.toByte()
        out[3] = cmd.toByte()
        out[4] = (seq and 0xFF).toByte()
        out[5] = ((seq ushr 8) and 0xFF).toByte()
        out[6] = (payload.size and 0xFF).toByte()
        out[7] = ((payload.size ushr 8) and 0xFF).toByte()
        payload.copyInto(out, HEADER)
        val crc = crc16(out, 2, HEADER + payload.size)
        out[HEADER + payload.size] = (crc and 0xFF).toByte()
        out[HEADER + payload.size + 1] = ((crc ushr 8) and 0xFF).toByte()
        return out
    }

    /** 一次 notify 最多带多少字节。MTU 未知(0) 时退到 BLE 最小 MTU 23 → 20 字节。 */
    fun notifyChunk(mtu: Int, remaining: Int): Int {
        val m = if (mtu > ATT_HEADER) mtu - ATT_HEADER else 20
        return if (remaining < m) remaining else m
    }
}
```

- [ ] **Step 4: 跑测试，确认通过**

Run: `cd android && /home/bit/tools/gradle-9.7.1/bin/gradle :app:testDebugUnitTest`
Expected: `BUILD SUCCESSFUL`，`ProtoTest` 4 个用例全过。

- [ ] **Step 5: 提交**

```bash
git add android/app/src/main/java/com/gpcombine/assistant/proto/Proto.kt \
        android/app/src/test/java/com/gpcombine/assistant/proto/ProtoTest.kt
git commit -m "feat(android): 协议核常数、CRC 与组帧

测试向量直接取自 2026-09-20 真机串口日志里设备自己打出的 WR->frame，不是手算的，
和固件 tools/host_tests 的断言同源。跑通这组就证明 App 和板子的字节布局一致。"
```

---

## Task 3: 增量收帧器

**Files:**
- Create: `android/app/src/main/java/com/gpcombine/assistant/proto/FrameParser.kt`
- Test: `android/app/src/test/java/com/gpcombine/assistant/proto/FrameParserTest.kt`

**Interfaces:**
- Consumes: `Proto`（Task 2）
- Produces:
  - `data class Frame(val cmd: Int, val seq: Int, val payload: ByteArray)`
  - `class FrameParser { fun push(b: Byte): Frame?; fun reset() }`

**为什么必须自己写收帧器而不是"读到多少算多少"**：MTU 只有 23 时，设备一个 INFO 回包（约 90 字节）会被切成 5 条独立 notify 到手机，每条都是残帧；而且 notify 是流式的，不能假设一次回调就是一帧。固件侧的收帧器也是同一个算法，坏字节靠 `A5 5A` 重新同步而不是整段丢弃。

- [ ] **Step 1: 写失败的测试**

```kotlin
package com.gpcombine.assistant.proto

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertNotNull
import org.junit.Test

class FrameParserTest {
    private fun hex(s: String) = s.trim().split(" ").map { it.toInt(16).toByte() }.toByteArray()

    private fun feed(p: FrameParser, bytes: ByteArray): List<Frame> {
        val out = mutableListOf<Frame>()
        for (b in bytes) p.push(b)?.let { out += it }
        return out
    }

    @Test
    fun parsesSingleFrame() {
        val got = feed(FrameParser(), hex("A5 5A 01 01 00 00 00 00 E1 E1"))
        assertEquals(1, got.size)
        assertEquals(Proto.CMD_PING, got[0].cmd)
        assertEquals(0, got[0].seq)
        assertEquals(0, got[0].payload.size)
    }

    /** MTU 23 时 INFO 回包会被切成 20 字节一片，逐片喂进来必须只吐一帧。 */
    @Test
    fun reassemblesFragmentedFrame() {
        val payload = "ver=a;app=1;fs=2/3;ram=4;psram=5".toByteArray()
        val frame = Proto.build(Proto.CMD_INFO, 7, payload)
        val p = FrameParser()
        val got = mutableListOf<Frame>()
        var off = 0
        while (off < frame.size) {
            val chunk = Proto.notifyChunk(23, frame.size - off)
            for (i in off until off + chunk) p.push(frame[i])?.let { got += it }
            off += chunk
            // 分片中间绝不能提前吐帧
            if (off < frame.size) assertEquals("分片中途不该出帧", 0, got.size)
        }
        assertEquals(1, got.size)
        assertEquals(Proto.CMD_INFO, got[0].cmd)
        assertEquals(7, got[0].seq)
        assertEquals(String(payload), String(got[0].payload))
    }

    @Test
    fun dropsGarbageAndResyncs() {
        // 前面 3 个坏字节 + 后面一帧，必须还能认出那一帧
        val bytes = hex("00 FF A5") + hex("A5 5A 01 01 00 00 00 00 E1 E1")
        val got = feed(FrameParser(), bytes)
        assertEquals("坏字节后应重新同步", 1, got.size)
        assertEquals(Proto.CMD_PING, got[0].cmd)
    }

    @Test
    fun rejectsBadCrc() {
        // 把 CRC 最后一字节改掉
        val bad = hex("A5 5A 01 01 00 00 00 00 E1 E0")
        assertNull("CRC 不对不能吐帧", feed(FrameParser(), bad).firstOrNull())
    }

    @Test
    fun rejectsOversizedLength() {
        // len=0x0200=512 > MAX_PAYLOAD(256)，应当丢掉而不是等 512 字节
        val bytes = hex("A5 5A 01 01 00 00 00 02") 
        assertNull(feed(FrameParser(), bytes).firstOrNull())
    }

    @Test
    fun parsesTwoFramesInOneStream() {
        val stream = Proto.build(Proto.CMD_PING, 1) + Proto.build(Proto.CMD_CFG_GET, 2)
        val got = feed(FrameParser(), stream)
        assertEquals(2, got.size)
        assertEquals(Proto.CMD_PING, got[0].cmd)
        assertEquals(Proto.CMD_CFG_GET, got[1].cmd)
    }

    @Test
    fun resetClearsHalfFrame() {
        val p = FrameParser()
        feed(p, hex("A5 5A 01 01 00 00 00 00 E1"))
        p.reset()
        assertNotNull(feed(p, hex("A5 5A 01 01 00 00 00 00 E1 E1"))[0])
    }
}
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `cd android && /home/bit/tools/gradle-9.7.1/bin/gradle :app:testDebugUnitTest`
Expected: 编译失败，`unresolved reference: FrameParser`。

- [ ] **Step 3: 实现 FrameParser.kt**

算法与固件 `proto.h` 的 `ProtoRx::tryParse` 完全一致：只认队首那一帧；魔数/长度/CRC 任何一处不对就把队首挪掉一格重找，这样混进垃圾或半个残帧也能自己走回来。

```kotlin
package com.gpcombine.assistant.proto

data class Frame(val cmd: Int, val seq: Int, val payload: ByteArray) {
    override fun equals(other: Any?): Boolean =
        other is Frame && cmd == other.cmd && seq == other.seq && payload.contentEquals(other.payload)

    override fun hashCode(): Int = (cmd * 31 + seq) * 31 + payload.contentHashCode()
}

class FrameParser {
    private val buf = ByteArray(Proto.HEADER + Proto.MAX_PAYLOAD + 2)
    private var have = 0

    fun reset() {
        have = 0
    }

    fun push(b: Byte): Frame? {
        if (have >= buf.size) dropFront(1)
        buf[have++] = b
        return tryParse()
    }

    private fun dropFront(n: Int) {
        System.arraycopy(buf, n, buf, 0, have - n)
        have -= n
    }

    private fun tryParse(): Frame? {
        while (true) {
            if (have < 2) return null
            if (buf[0] != Proto.MAGIC0.toByte() || buf[1] != Proto.MAGIC1.toByte()) {
                dropFront(1)
                continue
            }
            if (have < Proto.HEADER) return null

            val len = (buf[6].toInt() and 0xFF) or ((buf[7].toInt() and 0xFF) shl 8)
            if (len > Proto.MAX_PAYLOAD) {
                dropFront(1)
                continue
            }
            val total = Proto.HEADER + len + 2
            if (have < total) return null

            val crcRx = (buf[total - 2].toInt() and 0xFF) or ((buf[total - 1].toInt() and 0xFF) shl 8)
            val crcCalc = Proto.crc16(buf, 2, Proto.HEADER + len)
            if (crcRx != crcCalc) {
                dropFront(1)
                continue
            }

            val frame = Frame(
                cmd = buf[3].toInt() and 0xFF,
                seq = (buf[4].toInt() and 0xFF) or ((buf[5].toInt() and 0xFF) shl 8),
                payload = buf.copyOfRange(Proto.HEADER, Proto.HEADER + len),
            )
            dropFront(total)
            return frame
        }
    }
}
```

- [ ] **Step 4: 跑测试，确认通过**

Run: `cd android && /home/bit/tools/gradle-9.7.1/bin/gradle :app:testDebugUnitTest`
Expected: `FrameParserTest` 7 个用例全过。

- [ ] **Step 5: 提交**

```bash
git add android/app/src/main/java/com/gpcombine/assistant/proto/FrameParser.kt \
        android/app/src/test/java/com/gpcombine/assistant/proto/FrameParserTest.kt
git commit -m "feat(android): 增量收帧器，支持分片重组与坏字节重同步

MTU 只有 23 时一个 INFO 回包会被切成 5 条 notify，每条都是残帧，
所以不能假设一次回调就是一帧。算法与固件 proto.h 的 ProtoRx 一致。"
```

---

## Task 4: INFO / PAIR_INFO 键值解析

**Files:**
- Create: `android/app/src/main/java/com/gpcombine/assistant/proto/InfoCodec.kt`
- Test: `android/app/src/test/java/com/gpcombine/assistant/proto/InfoCodecTest.kt`

**Interfaces:**
- Consumes: 无
- Produces:
  - `data class DeviceInfo(val version: String, val appBytes: Long, val fsTotal: Long, val fsUsed: Long, val ramFree: Long, val psramFree: Long)`
  - `data class PairInfo(val name: String, val pairCode: String, val btEnabled: Boolean, val clients: Int, val apEnabled: Boolean)`
  - `InfoCodec.parseInfo(s: String): DeviceInfo`
  - `InfoCodec.parsePairInfo(s: String): PairInfo`

固件回的是**键值 ASCII 串**（`esp32_170x320.ino` 的 `netHandleFrame`）：

```
CMD_INFO      → "ver=%s;app=%u;fs=%u/%u;ram=%u;psram=%u"         // fs 是 总量/已用
CMD_PAIR_INFO → "name=%s;pair=%s;bt=%d;clients=%d;ap=0"
```

注意 `fs` 的值里本身带 `/`，所以要先按 `;` 切字段、再按 `=` 切键值，最后才把 `fs` 的值按 `/` 切两半。顺序弄反是这类解析最经典的 bug，下面专门有测试钉它。

- [ ] **Step 1: 写失败的测试**

```kotlin
package com.gpcombine.assistant.proto

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class InfoCodecTest {
    @Test
    fun parsesInfoFromFirmware() {
        // 格式与固件 netHandleFrame 里的 snprintf 完全一致
        val info = InfoCodec.parseInfo("ver=1.0.0;app=825776;fs=12517376/2540000;ram=67056;psram=5588080")
        assertEquals("1.0.0", info.version)
        assertEquals(825776L, info.appBytes)
        assertEquals(12517376L, info.fsTotal)
        assertEquals(2540000L, info.fsUsed)
        assertEquals(67056L, info.ramFree)
        assertEquals(5588080L, info.psramFree)
    }

    /** 总量和已用写反了会显示成"卡快满了"，专门用两个量级差很大的数钉住顺序。 */
    @Test
    fun fsKeepsTotalBeforeUsed() {
        val info = InfoCodec.parseInfo("ver=v;app=1;fs=100/3;ram=1;psram=1")
        assertEquals(100L, info.fsTotal)
        assertEquals(3L, info.fsUsed)
    }

    @Test
    fun parsesPairInfoFromFirmware() {
        val p = InfoCodec.parsePairInfo("name=GP-Combine-72E0;pair=280148;bt=1;clients=1;ap=0")
        assertEquals("GP-Combine-72E0", p.name)
        assertEquals("280148", p.pairCode)
        assertEquals(true, p.btEnabled)
        assertEquals(1, p.clients)
        assertEquals(false, p.apEnabled)
    }

    @Test
    fun ignoresUnknownKeys() {
        val info = InfoCodec.parseInfo("ver=1;app=1;fs=1/1;ram=1;psram=1;future=42")
        assertEquals("1", info.version)
    }

    @Test
    fun throwsOnMissingField() {
        val e = assertThrows(IllegalArgumentException::class.java) {
            InfoCodec.parseInfo("ver=1;app=1;ram=1;psram=1") // 少了 fs
        }
        assertEquals(true, e.message!!.contains("fs"))
    }
}
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `cd android && /home/bit/tools/gradle-9.7.1/bin/gradle :app:testDebugUnitTest`
Expected: 编译失败，`unresolved reference: InfoCodec`。

- [ ] **Step 3: 实现 InfoCodec.kt**

```kotlin
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
```

- [ ] **Step 4: 跑测试，确认通过**

Run: `cd android && /home/bit/tools/gradle-9.7.1/bin/gradle :app:testDebugUnitTest`
Expected: `InfoCodecTest` 5 个用例全过。

- [ ] **Step 5: 提交**

```bash
git add android/app/src/main/java/com/gpcombine/assistant/proto/InfoCodec.kt \
        android/app/src/test/java/com/gpcombine/assistant/proto/InfoCodecTest.kt
git commit -m "feat(android): 解析固件的 INFO / PAIR_INFO 键值串

固件回的是 ASCII 键值串而不是二进制，照原样解析即可。fs 字段的值里自带 '/'，
所以切分顺序必须是先 ';' 再 '=' 最后才按 '/'，测试专门钉了总量/已用的顺序。
缺字段直接抛异常，不返回 0——界面上的假 0 比报错难查。"
```

---

## Task 5: 传输抽象 + 会话层（seq 配对的请求-响应）

**Files:**
- Create: `android/app/src/main/java/com/gpcombine/assistant/ble/BleTransport.kt`
- Create: `android/app/src/main/java/com/gpcombine/assistant/ble/FakeTransport.kt`
- Create: `android/app/src/main/java/com/gpcombine/assistant/net/DeviceClient.kt`
- Test: `android/app/src/test/java/com/gpcombine/assistant/net/DeviceClientTest.kt`

**Interfaces:**
- Consumes: `Proto`, `Frame`, `FrameParser`（Task 2/3）、`InfoCodec`, `DeviceInfo`, `PairInfo`（Task 4）
- Produces:
  - `enum class BleState { IDLE, SCANNING, CONNECTING, CONNECTED, DISCONNECTED }`
  - `interface BleTransport { val inbound: Flow<Frame>; val state: StateFlow<BleState>; suspend fun send(frame: ByteArray) }`
  - `class FakeTransport(pairCode: String = "280148") : BleTransport`，另有 `fun connect()`
  - `class DeviceException(code: Int, message: String) : Exception`
  - `class DeviceClient(transport: BleTransport, scope: CoroutineScope, timeoutMs: Long = 3000)`
    带 `suspend fun ping(): Boolean` / `auth(code: String): Boolean` / `info(): DeviceInfo` / `pairInfo(): PairInfo` / `fun close()`

请求-响应靠 `seq` 配对：每个请求自增一个 seq，设备回包原样带回 seq，客户端用它把回包对上号。设备侧一次只处理一帧，所以客户端**串行发请求**（`Mutex` 保护），不并发。

- [ ] **Step 1: 写失败的测试**

```kotlin
package com.gpcombine.assistant.net

import com.gpcombine.assistant.ble.BleState
import com.gpcombine.assistant.ble.BleTransport
import com.gpcombine.assistant.ble.FakeTransport
import com.gpcombine.assistant.proto.Frame
import com.gpcombine.assistant.proto.Proto
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DeviceClientTest {
    private fun TestScope.client(t: BleTransport) = DeviceClient(t, backgroundScope, timeoutMs = 1000)

    @Test
    fun pingRoundTrip() = runTest {
        val t = FakeTransport().apply { connect() }
        assertTrue(client(t).ping())
    }

    @Test
    fun authAcceptsOnlyTheRightCode() = runTest {
        val t = FakeTransport("280148").apply { connect() }
        val c = client(t)
        assertFalse("错的码必须返回 false", c.auth("000000"))
        assertTrue("对的码必须返回 true", c.auth("280148"))
    }

    @Test
    fun infoParsesAfterAuth() = runTest {
        val t = FakeTransport().apply { connect() }
        val c = client(t)
        c.auth("280148")
        assertEquals("0.0.0-fake", c.info().version)
        assertEquals(12517376L, c.info().fsTotal)
    }

    /** 没认证就查 INFO，设备回 ERR_NOT_AUTHED，客户端要把它变成带错误码的异常。 */
    @Test
    fun unauthenticatedCommandRaisesDeviceException() = runTest {
        val t = FakeTransport().apply { connect() }
        val c = client(t)
        val e = runCatching { c.info() }.exceptionOrNull()
        assertTrue("应该是 DeviceException，实际 $e", e is DeviceException)
        assertEquals(Proto.ERR_NOT_AUTHED, (e as DeviceException).code)
    }

    @Test
    fun timesOutWhenDeviceNeverAnswers() = runTest {
        val silent = object : BleTransport {
            override val inbound = MutableSharedFlow<Frame>()
            override val state = MutableStateFlow(BleState.CONNECTED)
            override suspend fun send(frame: ByteArray) = Unit
        }
        val e = runCatching { client(silent).ping() }.exceptionOrNull()
        assertTrue("应该是超时，实际 $e", e is TimeoutCancellationException)
    }

    /** seq 必须自增，否则两次请求的回包会互相串台。 */
    @Test
    fun seqIncrementsBetweenRequests() = runTest {
        val seen = mutableListOf<Int>()
        val t = object : BleTransport {
            override val inbound = MutableSharedFlow<Frame>()
            override val state = MutableStateFlow(BleState.CONNECTED)
            override suspend fun send(frame: ByteArray) {
                val p = FrameParser()
                frame.forEach { b -> p.push(b)?.let { f -> seen += f.seq } }
            }
        }
        val c = DeviceClient(t, backgroundScope, timeoutMs = 50)
        // 这个 transport 不回包，三次请求必然超时；本用例只关心发出去的 seq
        runCatching { c.ping() }
        runCatching { c.ping() }
        runCatching { c.ping() }
        assertEquals(listOf(0, 1, 2), seen)
    }
}
```

测试文件顶部还要 `import com.gpcombine.assistant.proto.FrameParser`。

- [ ] **Step 2: 跑测试，确认失败**

Run: `cd android && /home/bit/tools/gradle-9.7.1/bin/gradle :app:testDebugUnitTest`
Expected: 编译失败，`unresolved reference: FakeTransport`。

- [ ] **Step 3: 实现 BleTransport.kt**

```kotlin
package com.gpcombine.assistant.ble

import com.gpcombine.assistant.proto.Frame
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.StateFlow

enum class BleState { IDLE, SCANNING, CONNECTING, CONNECTED, DISCONNECTED }

/**
 * BLE 收发藏在接口后面：真机实现要蓝牙栈和运行时权限，FakeTransport 什么都不需要，
 * 所以 UI 和会话逻辑可以在没有板子的机器上跑测试。
 */
interface BleTransport {
    /** 收帧流。分片重组已经在实现里做完，这里吐出来的一定是完整帧。 */
    val inbound: Flow<Frame>
    val state: StateFlow<BleState>
    suspend fun send(frame: ByteArray)
}
```

- [ ] **Step 4: 实现 FakeTransport.kt**

行为照抄固件 `netHandleFrame`：PING 原样回；AUTH 校验 6 位码；其余命令没认证时报 `ERR_NOT_AUTHED`。

```kotlin
package com.gpcombine.assistant.ble

import com.gpcombine.assistant.proto.Frame
import com.gpcombine.assistant.proto.FrameParser
import com.gpcombine.assistant.proto.Proto
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow

class FakeTransport(private val pairCode: String = "280148") : BleTransport {
    private val _inbound = MutableSharedFlow<Frame>(extraBufferCapacity = 16)
    override val inbound: Flow<Frame> = _inbound.asSharedFlow()

    private val _state = MutableStateFlow(BleState.IDLE)
    override val state: StateFlow<BleState> = _state.asStateFlow()

    private var authed = false

    fun connect() {
        authed = false
        _state.value = BleState.CONNECTED
    }

    override suspend fun send(frame: ByteArray) {
        val parser = FrameParser()
        val req = frame.firstNotNullOfOrNull { parser.push(it) } ?: return
        _inbound.emit(reply(req))
    }

    private fun err(seq: Int, code: Int, text: String) =
        Frame(Proto.CMD_ERR, seq, byteArrayOf(code.toByte()) + text.toByteArray())

    private fun reply(req: Frame): Frame = when {
        req.cmd == Proto.CMD_PING -> Frame(Proto.CMD_PING, req.seq, req.payload)

        req.cmd == Proto.CMD_AUTH -> {
            val ok = String(req.payload, Charsets.US_ASCII) == pairCode
            if (ok) authed = true
            Frame(Proto.CMD_AUTH, req.seq, byteArrayOf(if (ok) 1 else 0))
        }

        !authed -> err(req.seq, Proto.ERR_NOT_AUTHED, "auth first")

        req.cmd == Proto.CMD_INFO -> Frame(
            Proto.CMD_INFO, req.seq,
            "ver=0.0.0-fake;app=825776;fs=12517376/2540000;ram=67056;psram=5588080".toByteArray(),
        )

        req.cmd == Proto.CMD_PAIR_INFO -> Frame(
            Proto.CMD_PAIR_INFO, req.seq,
            "name=GP-Combine-FAKE;pair=$pairCode;bt=1;clients=1;ap=0".toByteArray(),
        )

        else -> err(req.seq, Proto.ERR_UNKNOWN_CMD, "unknown cmd")
    }
}
```

- [ ] **Step 5: 实现 DeviceClient.kt**

```kotlin
package com.gpcombine.assistant.net

import com.gpcombine.assistant.ble.BleTransport
import com.gpcombine.assistant.proto.DeviceInfo
import com.gpcombine.assistant.proto.Frame
import com.gpcombine.assistant.proto.InfoCodec
import com.gpcombine.assistant.proto.PairInfo
import com.gpcombine.assistant.proto.Proto
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withTimeout

/** 设备回了错误帧（0x7F）。code 见 Proto.ERR_*。 */
class DeviceException(val code: Int, override val message: String) : Exception(message)

/**
 * 会话层：把"发一帧、等同一 seq 的回包"封装起来。
 *
 * 串行发送（Mutex）而不是并发：设备侧处理在主循环里，一次只推进一帧，
 * 并发发请求只会堆在它的接收队列里，回包顺序还可能和请求顺序不一致。
 *
 * pending 只在 collector 和 request 里访问，两者都跑在传入的 scope 上，
 * 所以用普通 MutableMap 就够（不要换成多线程 dispatcher）。
 */
class DeviceClient(
    private val transport: BleTransport,
    scope: CoroutineScope,
    private val timeoutMs: Long = 3000,
) {
    private val pending = mutableMapOf<Int, CompletableDeferred<Frame>>()
    private val lock = Mutex()
    private var nextSeq = 0

    private val collector: Job = scope.launch {
        transport.inbound.collect { onFrame(it) }
    }

    fun close() {
        collector.cancel()
        pending.values.forEach { it.cancel() }
        pending.clear()
    }

    private fun onFrame(f: Frame) {
        val d = pending[f.seq] ?: return
        if (f.cmd == Proto.CMD_ERR) {
            val code = if (f.payload.isNotEmpty()) f.payload[0].toInt() and 0xFF else -1
            val text = if (f.payload.size > 1) String(f.payload, 1, f.payload.size - 1) else ""
            d.completeExceptionally(DeviceException(code, text))
        } else {
            d.complete(f)
        }
    }

    private suspend fun request(cmd: Int, payload: ByteArray = Proto.EMPTY): Frame = lock.withLock {
        val seq = nextSeq and 0xFFFF
        nextSeq++
        val d = CompletableDeferred<Frame>()
        pending[seq] = d
        try {
            transport.send(Proto.build(cmd, seq, payload))
            withTimeout(timeoutMs) { d.await() }
        } finally {
            pending.remove(seq)
        }
    }

    suspend fun ping(): Boolean = request(Proto.CMD_PING).cmd == Proto.CMD_PING

    suspend fun auth(code: String): Boolean {
        val f = request(Proto.CMD_AUTH, code.toByteArray(Charsets.US_ASCII))
        return f.payload.isNotEmpty() && f.payload[0].toInt() == 1
    }

    suspend fun info(): DeviceInfo =
        InfoCodec.parseInfo(String(request(Proto.CMD_INFO).payload, Charsets.US_ASCII))

    suspend fun pairInfo(): PairInfo =
        InfoCodec.parsePairInfo(String(request(Proto.CMD_PAIR_INFO).payload, Charsets.US_ASCII))
}
```

- [ ] **Step 6: 跑测试，确认通过**

Run: `cd android && /home/bit/tools/gradle-9.7.1/bin/gradle :app:testDebugUnitTest`
Expected: `DeviceClientTest` 6 个用例全过。

- [ ] **Step 7: 提交**

```bash
git add android/app/src/main/java/com/gpcombine/assistant/ble/ \
        android/app/src/main/java/com/gpcombine/assistant/net/ \
        android/app/src/test/java/com/gpcombine/assistant/net/
git commit -m "feat(android): BLE 传输抽象、假设备与会话层

BleTransport 接口把真机蓝牙和 UI 隔开：真机实现要权限和蓝牙栈，FakeTransport
照抄固件 netHandleFrame 的行为，于是没有板子也能跑通整条会话逻辑。
DeviceClient 用 seq 配对请求与回包，串行发送——设备侧一次只推进一帧。"
```

---

## Task 6: 真机 BLE 层

**Files:**
- Create: `android/app/src/main/java/com/gpcombine/assistant/ble/AndroidBleTransport.kt`

**Interfaces:**
- Consumes: `BleTransport`, `BleState`（Task 5）、`Frame`, `FrameParser`（Task 3）
- Produces:
  - `data class ScannedDevice(val name: String, val address: String, val rssi: Int)`
  - `class AndroidBleTransport(context: Context) : BleTransport`
    额外提供 `fun scan(): Flow<ScannedDevice>`、`suspend fun connect(address: String)`、`fun close()`

**这一层没法单测**：本机没有蓝牙适配器，Android BLE 也只能在真机上跑。所以它的正确性靠三条保证——① 逻辑尽量薄（不解析协议，只搬运字节，解析全在 Task 3 的纯 Kotlin 层）；② 收包直接复用 Task 3 的 `FrameParser`，分片重组已经测过；③ 真机验收（Task 8）覆盖它。

**两个必须写对的细节**：

1. **必须订阅 TX（`...0003`）并写 CCCD**，否则设备的 notify 会一直失败——固件那边连续失败 20 次就整帧丢掉。这是今天在 nRF Connect 上已经踩过的坑。
2. **MTU 协商失败也不影响 M1**：`requestMtu(247)` 万一只协商到 23，设备会按 20 字节一片发，`FrameParser` 照样能拼回一个约 90 字节的 INFO 帧。这是设计上留的容错，不是运气。

- [ ] **Step 1: 实现 AndroidBleTransport.kt**

```kotlin
package com.gpcombine.assistant.ble

import android.Manifest
import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.content.ContextCompat
import com.gpcombine.assistant.proto.Frame
import com.gpcombine.assistant.proto.FrameParser
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.callbackFlow
import java.util.UUID

data class ScannedDevice(val name: String, val address: String, val rssi: Int)

class AndroidBleTransport(private val context: Context) : BleTransport {
    companion object {
        // Nordic UART Service：手机端不写自定义服务也能用 nRF Connect 手测，固件侧同一套 UUID
        val SERVICE: UUID = UUID.fromString("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
        val RX: UUID = UUID.fromString("6E400002-B5A3-F393-E0A9-E50E24DCCA9E") // 手机 → 设备（写）
        val TX: UUID = UUID.fromString("6E400003-B5A3-F393-E0A9-E50E24DCCA9E") // 设备 → 手机（订阅）
        val CCCD: UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")
        const val NAME_PREFIX = "GP-Combine-"
        const val REQUEST_MTU = 247
        private const val ATT_HEADER = 3
    }

    private val _inbound = MutableSharedFlow<Frame>(extraBufferCapacity = 32)
    override val inbound: Flow<Frame> = _inbound.asSharedFlow()

    private val _state = MutableStateFlow(BleState.IDLE)
    override val state: StateFlow<BleState> = _state.asStateFlow()

    private var gatt: BluetoothGatt? = null
    private var rxChar: BluetoothGattCharacteristic? = null
    private var mtu = 23
    private var parser = FrameParser()

    // ---- 权限 ----

    /** Android 12(31)+ 要「附近设备」，11 及以下扫 BLE 要定位。 */
    private fun missingPermissions(): List<String> {
        val needed = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            listOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
        } else {
            listOf(Manifest.permission.ACCESS_FINE_LOCATION)
        }
        return needed.filter {
            ContextCompat.checkSelfPermission(context, it) != PackageManager.PERMISSION_GRANTED
        }
    }

    private fun requirePermissions() {
        val missing = missingPermissions()
        check(missing.isEmpty()) { "缺少蓝牙权限：${missing.joinToString()}" }
    }

    private fun requireAdapter(): BluetoothAdapter {
        requirePermissions()
        val mgr = context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
        return mgr.adapter ?: error("这台手机没有蓝牙适配器")
    }

    // ---- 扫描 ----

    @SuppressLint("MissingPermission")
    fun scan(): Flow<ScannedDevice> = callbackFlow {
        val adapter = requireAdapter()
        check(adapter.isEnabled) { "蓝牙没打开" }
        val scanner = adapter.bluetoothLeScanner ?: error("拿不到 BLE 扫描器")

        val cb = object : ScanCallback() {
            override fun onScanResult(callbackType: Int, result: ScanResult) {
                val name = result.device.name ?: return
                if (!name.startsWith(NAME_PREFIX)) return
                trySend(ScannedDevice(name, result.device.address, result.rssi))
            }
        }

        _state.value = BleState.SCANNING
        scanner.startScan(
            null,
            ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build(),
            cb,
        )
        awaitClose {
            scanner.stopScan(cb)
            if (_state.value == BleState.SCANNING) _state.value = BleState.IDLE
        }
    }

    // ---- 连接 ----

    @SuppressLint("MissingPermission")
    suspend fun connect(address: String) {
        val adapter = requireAdapter()
        _state.value = BleState.CONNECTING
        parser = FrameParser()
        val device = adapter.getRemoteDevice(address)
        gatt = device.connectGatt(context, false, gattCallback, BluetoothDevice.TRANSPORT_LE)
    }

    private val gattCallback = object : BluetoothGattCallback() {
        @SuppressLint("MissingPermission")
        override fun onConnectionStateChange(g: BluetoothGatt, status: Int, newState: Int) {
            if (newState == BluetoothProfile.STATE_CONNECTED) {
                g.requestMtu(REQUEST_MTU)
                g.discoverServices()
            } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                rxChar = null
                _state.value = BleState.DISCONNECTED
            }
        }

        @SuppressLint("MissingPermission")
        override fun onServicesDiscovered(g: BluetoothGatt, status: Int) {
            val svc = g.getService(SERVICE) ?: run {
                _state.value = BleState.DISCONNECTED
                return
            }
            rxChar = svc.getCharacteristic(RX)
            val tx = svc.getCharacteristic(TX)
            if (rxChar == null || tx == null) {
                _state.value = BleState.DISCONNECTED
                return
            }
            // 不订阅 TX，设备的 notify 会一直失败，连续 20 次后整帧丢弃 —— 现象是"发出去没回包"
            g.setCharacteristicNotification(tx, true)
            val cccd = tx.getDescriptor(CCCD)
            if (cccd != null) {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    g.writeDescriptor(cccd, BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE)
                } else {
                    @Suppress("DEPRECATION")
                    cccd.value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
                    @Suppress("DEPRECATION")
                    g.writeDescriptor(cccd)
                }
            }
            g.requestConnectionPriority(BluetoothGatt.CONNECTION_PRIORITY_HIGH)
            _state.value = BleState.CONNECTED
        }

        override fun onMtuChanged(g: BluetoothGatt, newMtu: Int, status: Int) {
            mtu = newMtu
        }

        @Deprecated("Android 13 起走新签名")
        override fun onCharacteristicChanged(
            g: BluetoothGatt,
            ch: BluetoothGattCharacteristic,
        ) {
            @Suppress("DEPRECATION")
            feed(ch.value ?: return)
        }

        override fun onCharacteristicChanged(
            g: BluetoothGatt,
            ch: BluetoothGattCharacteristic,
            value: ByteArray,
        ) {
            feed(value)
        }
    }

    /** 把一段 notify 数据喂给分片重组器，攒够一整帧才吐出去。 */
    private fun feed(bytes: ByteArray) {
        for (b in bytes) parser.push(b)?.let { _inbound.tryEmit(it) }
    }

    // ---- 发送 ----

    @SuppressLint("MissingPermission")
    override suspend fun send(frame: ByteArray) {
        val g = gatt ?: error("还没连上设备")
        val ch = rxChar ?: error("还没发现 RX 特征")
        val max = mtu - ATT_HEADER
        require(frame.size <= max) { "一帧 ${frame.size} 字节超过 MTU $mtu 能带的 $max 字节" }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            g.writeCharacteristic(
                ch, frame, BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE,
            )
        } else {
            @Suppress("DEPRECATION")
            ch.writeType = BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE
            @Suppress("DEPRECATION")
            ch.value = frame
            @Suppress("DEPRECATION")
            g.writeCharacteristic(ch)
        }
    }

    @SuppressLint("MissingPermission")
    fun close() {
        gatt?.close()
        gatt = null
        rxChar = null
        _state.value = BleState.IDLE
    }
}
```

- [ ] **Step 2: 编译**

Run: `cd android && /home/bit/tools/gradle-9.7.1/bin/gradle :app:assembleDebug`
Expected: `BUILD SUCCESSFUL`。这一步只能证明它能编译，**行为要等 Task 8 上真机**。

如果报 `onCharacteristicChanged` 重复定义，说明 `@Deprecated` 注解用错了位置——那个旧签名要保留（minSdk 29 的机器走它），新签名是无覆写注解的重载。

- [ ] **Step 3: 提交**

```bash
git add android/app/src/main/java/com/gpcombine/assistant/ble/AndroidBleTransport.kt
git commit -m "feat(android): 真机 BLE 收发层

逻辑刻意做薄：只搬运字节，协议解析全在已测过的纯 Kotlin 层。
onServicesDiscovered 里写了 CCCD 订阅 TX——不订阅的话设备 notify 会连续失败 20 次后丢帧，
现象是发出去没回包（今天在 nRF Connect 上已经踩过）。
MTU 协商失败也不影响 M1：设备按 20 字节分片，收帧器照样拼得回完整帧。"
```

---

## Task 7: 界面、权限与 ViewModel

**Files:**
- Create: `android/app/src/main/java/com/gpcombine/assistant/store/Prefs.kt`
- Create: `android/app/src/main/java/com/gpcombine/assistant/ui/Theme.kt`
- Create: `android/app/src/main/java/com/gpcombine/assistant/ui/DeviceViewModel.kt`
- Create: `android/app/src/main/java/com/gpcombine/assistant/ui/Screens.kt`
- Modify: `android/app/src/main/java/com/gpcombine/assistant/ui/MainActivity.kt`

**Interfaces:**
- Consumes: `DeviceClient`, `DeviceException`（Task 5）、`AndroidBleTransport`, `ScannedDevice`（Task 6）、`DeviceInfo`, `PairInfo`（Task 4）
- Produces:
  - `class Prefs(context: Context) { var lastAddress: String?; var pairCode: String? }`
  - `enum class Phase { IDLE, SCANNING, NEED_CODE, WORKING, READY }`
  - `data class UiState(phase, devices, deviceName, info, pair, error)`
  - `class DeviceViewModel(app: Application, useFake: Boolean) : AndroidViewModel`，
    带 `val ui: StateFlow<UiState>`、`fun startScan()`、`fun connect(ScannedDevice)`、`fun submitCode(String)`、`fun refresh()`
  - `@Composable fun GPCombineTheme(content: @Composable () -> Unit)`
  - `@Composable fun ConnectScreen(...)` / `@Composable fun DeviceScreen(...)` / `@Composable fun PermissionScreen(...)`

**权限按 SDK 分支，两件事要分开**（这是最容易写错的地方）：
- **申请什么**：按用户要求三件套全申请 —— 31+ 是 `BLUETOOTH_SCAN` + `BLUETOOTH_CONNECT` + `ACCESS_FINE_LOCATION`；30 及以下是 `ACCESS_FINE_LOCATION`。
- **拦不拦人**：只检查**真正必需**的。31+ 只要前两个就够了，用户拒绝了定位权限不该把 App 挡在门外（那是给 30 及以下扫 BLE 用的）。

- [ ] **Step 1: 实现 Prefs.kt**

```kotlin
package com.gpcombine.assistant.store

import android.content.Context

/** 记住上次连的设备和配对码，省得每次重输。M1 只存这两个，够用就行。 */
class Prefs(context: Context) {
    private val sp = context.getSharedPreferences("gpcombine", Context.MODE_PRIVATE)

    var lastAddress: String?
        get() = sp.getString("lastAddress", null)
        set(v) = sp.edit().putString("lastAddress", v).apply()

    var pairCode: String?
        get() = sp.getString("pairCode", null)
        set(v) = sp.edit().putString("pairCode", v).apply()
}
```

- [ ] **Step 2: 实现 Theme.kt**

```kotlin
package com.gpcombine.assistant.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val Colors = darkColorScheme(
    primary = Color(0xFF6FD3FF),
    onPrimary = Color(0xFF00344A),
    surface = Color(0xFF1B1B1F),
    background = Color(0xFF111114),
)

@Composable
fun GPCombineTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = Colors, content = content)
}
```

- [ ] **Step 3: 实现 DeviceViewModel.kt**

`useFake = true` 时用 `FakeTransport`，插件的调试入口是启动 Activity 时带 `--ez fake true`（`adb shell am start ... --ez fake true`），手机上也可以用一个调试按钮触发。没有板子也能把页面和状态机走通。

```kotlin
package com.gpcombine.assistant.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.gpcombine.assistant.ble.AndroidBleTransport
import com.gpcombine.assistant.ble.BleTransport
import com.gpcombine.assistant.ble.FakeTransport
import com.gpcombine.assistant.ble.ScannedDevice
import com.gpcombine.assistant.net.DeviceClient
import com.gpcombine.assistant.proto.DeviceInfo
import com.gpcombine.assistant.proto.PairInfo
import com.gpcombine.assistant.store.Prefs
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

enum class Phase { IDLE, SCANNING, NEED_CODE, WORKING, READY }

data class UiState(
    val phase: Phase = Phase.IDLE,
    val devices: List<ScannedDevice> = emptyList(),
    val deviceName: String = "",
    val info: DeviceInfo? = null,
    val pair: PairInfo? = null,
    val error: String? = null,
)

class DeviceViewModel(app: Application, private val useFake: Boolean) : AndroidViewModel(app) {
    private val transport: BleTransport =
        if (useFake) FakeTransport() else AndroidBleTransport(app)
    private val client = DeviceClient(transport, viewModelScope, timeoutMs = 4000)
    private val prefs = Prefs(app)

    private val _ui = MutableStateFlow(UiState())
    val ui: StateFlow<UiState> = _ui.asStateFlow()

    private var scanJob: Job? = null

    fun startScan() {
        scanJob?.cancel()
        _ui.update { it.copy(phase = Phase.SCANNING, devices = emptyList(), error = null) }

        val fake = transport as? FakeTransport
        if (fake != null) {
            fake.connect()
            _ui.update { it.copy(phase = Phase.NEED_CODE, deviceName = "GP-Combine-FAKE") }
            prefs.pairCode?.let { refresh() }
            return
        }

        val real = transport as AndroidBleTransport
        scanJob = viewModelScope.launch {
            runCatching {
                real.scan().collect { d ->
                    _ui.update { s -> s.copy(devices = (s.devices + d).distinctBy { it.address }) }
                }
            }.onFailure { e ->
                _ui.update { it.copy(phase = Phase.IDLE, error = e.message) }
            }
        }
    }

    fun connect(device: ScannedDevice) {
        scanJob?.cancel()
        scanJob = null
        _ui.update {
            it.copy(phase = Phase.WORKING, deviceName = device.name, error = null, devices = emptyList())
        }
        viewModelScope.launch {
            try {
                (transport as AndroidBleTransport).connect(device.address)
                prefs.lastAddress = device.address
                // 连接是异步完成的：等状态变 CONNECTED 再问配对码
                transport.state.collect { st ->
                    if (st == com.gpcombine.assistant.ble.BleState.CONNECTED) {
                        _ui.update { it.copy(phase = Phase.NEED_CODE) }
                    }
                }
            } catch (e: Exception) {
                _ui.update { it.copy(phase = Phase.IDLE, error = e.message) }
            }
        }
    }

    fun submitCode(code: String) {
        viewModelScope.launch {
            _ui.update { it.copy(phase = Phase.WORKING, error = null) }
            try {
                if (!client.auth(code)) {
                    _ui.update { it.copy(phase = Phase.NEED_CODE, error = "配对码不对，看设备屏幕") }
                    return@launch
                }
                prefs.pairCode = code
                loadDeviceInfo()
            } catch (e: Exception) {
                _ui.update { it.copy(phase = Phase.NEED_CODE, error = e.message) }
            }
        }
    }

    fun refresh() {
        viewModelScope.launch {
            _ui.update { it.copy(error = null) }
            try {
                loadDeviceInfo()
            } catch (e: Exception) {
                _ui.update { it.copy(error = e.message) }
            }
        }
    }

    private suspend fun loadDeviceInfo() {
        val info = client.info()
        val pair = client.pairInfo()
        _ui.update { it.copy(phase = Phase.READY, info = info, pair = pair, error = null) }
    }

    override fun onCleared() {
        client.close()
        (transport as? AndroidBleTransport)?.close()
    }

    companion object {
        fun factory(app: Application, useFake: Boolean) = viewModelFactory {
            initializer { DeviceViewModel(app, useFake) }
        }
    }
}
```

- [ ] **Step 4: 实现 Screens.kt**

```kotlin
package com.gpcombine.assistant.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.gpcombine.assistant.ble.ScannedDevice

@Composable
fun PermissionScreen(onRequest: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        Text("需要蓝牙权限", style = MaterialTheme.typography.titleLarge)
        Text("用来扫描并连接手柄上的蓝牙模块。Android 12 以下还需要定位权限，那是系统扫描蓝牙的硬性要求。")
        Button(onClick = onRequest, modifier = Modifier.padding(top = 16.dp)) { Text("去授权") }
    }
}

@Composable
fun ConnectScreen(
    ui: UiState,
    onScan: () -> Unit,
    onConnect: (ScannedDevice) -> Unit,
    onCode: (String) -> Unit,
) {
    var code by remember { mutableStateOf("") }

    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        Text("GP-Combine", style = MaterialTheme.typography.headlineSmall)
        ui.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }

        when (ui.phase) {
            Phase.SCANNING -> {
                Text("正在扫描…")
                LazyColumn(modifier = Modifier.fillMaxWidth().padding(top = 8.dp)) {
                    items(ui.devices) { d ->
                        Card(
                            modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)
                                .clickable { onConnect(d) },
                        ) { Text("${d.name}   ${d.rssi} dBm", Modifier.padding(12.dp)) }
                    }
                }
            }

            Phase.NEED_CODE -> {
                Text("设备：${ui.deviceName}")
                Text("输入设备屏幕上显示的 6 位配对码")
                OutlinedTextField(
                    value = code,
                    onValueChange = { if (it.length <= 6) code = it.filter(Char::isDigit) },
                    label = { Text("配对码") },
                    modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
                )
                Button(onClick = { onCode(code) }, enabled = code.length == 6) { Text("连接") }
            }

            Phase.WORKING -> Text("通信中…")

            Phase.READY -> DeviceInfoSection(ui)

            Phase.IDLE -> Button(onClick = onScan, modifier = Modifier.padding(top = 16.dp)) {
                Text("扫描设备")
            }
        }
    }
}

/** 设备页：把 INFO / PAIR_INFO 的字段摊开显示。 */
@Composable
fun DeviceInfoSection(ui: UiState) {
    val info = ui.info
    val pair = ui.pair
    Column(modifier = Modifier.fillMaxWidth().padding(top = 8.dp)) {
        Text("设备：${pair?.name ?: ui.deviceName}", style = MaterialTheme.typography.titleMedium)
        info?.let {
            Text("固件版本：${it.version}")
            Text("固件大小：${mb(it.appBytes)}")
            Text("卡空间：已用 ${mb(it.fsUsed)} / 共 ${mb(it.fsTotal)}")
            Text("内部 RAM 余：${kb(it.ramFree)}")
            Text("PSRAM 余：${mb(it.psramFree)}")
        }
        pair?.let {
            Text("配对码：${it.pairCode}")
            Text("蓝牙：${if (it.btEnabled) "开" else "关"}    已连手机：${it.clients}")
        }
    }
}

private fun mb(v: Long) = "%.1f MB".format(v / 1048576.0)
private fun kb(v: Long) = "%.1f KB".format(v / 1024.0)
```

`DeviceScreen` 这个名字在 Task 7 的 Interfaces 里写了，实际就复用了上面的 `DeviceInfoSection`（`Phase.READY` 分支直接渲染它）。命名以此处为准：不要另外再建一个空壳 `DeviceScreen`。

- [ ] **Step 5: 改 MainActivity.kt**

```kotlin
package com.gpcombine.assistant.ui

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel

/** 申请哪几个：按用户要求三件套全要（31+ 还要定位，虽然它不再必需）。 */
private fun permissionsToRequest(): Array<String> =
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
        arrayOf(
            Manifest.permission.BLUETOOTH_SCAN,
            Manifest.permission.BLUETOOTH_CONNECT,
            Manifest.permission.ACCESS_FINE_LOCATION,
        )
    } else {
        arrayOf(Manifest.permission.ACCESS_FINE_LOCATION)
    }

/** 拦不拦人：只认真正必需的。31+ 拒绝了定位权限不该挡住 App。 */
private fun hasRequiredPermissions(ctx: Context): Boolean {
    val required = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
        listOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
    } else {
        listOf(Manifest.permission.ACCESS_FINE_LOCATION)
    }
    return required.all {
        ContextCompat.checkSelfPermission(ctx, it) == PackageManager.PERMISSION_GRANTED
    }
}

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val useFake = intent?.getBooleanExtra("fake", false) == true

        setContent {
            GPCombineTheme {
                val ctx = LocalContext.current
                var granted by remember { mutableStateOf(hasRequiredPermissions(ctx)) }
                val launcher = rememberLauncherForActivityResult(
                    ActivityResultContracts.RequestMultiplePermissions(),
                ) { granted = hasRequiredPermissions(ctx) }

                if (!granted) {
                    PermissionScreen(onRequest = { launcher.launch(permissionsToRequest()) })
                } else {
                    val vm: DeviceViewModel = viewModel(
                        factory = DeviceViewModel.factory(application, useFake),
                    )
                    val ui by vm.ui.collectAsStateWithLifecycle()
                    ConnectScreen(
                        ui = ui,
                        onScan = vm::startScan,
                        onConnect = vm::connect,
                        onCode = vm::submitCode,
                    )
                }
            }
        }
    }
}
```

- [ ] **Step 6: 构建**

Run: `cd android && /home/bit/tools/gradle-9.7.1/bin/gradle :app:assembleDebug`
Expected: `BUILD SUCCESSFUL`。

- [ ] **Step 7: 提交**

```bash
git add android/app/src/main/java/com/gpcombine/assistant/
git commit -m "feat(android): 扫描/连接/配对码界面与 ViewModel

权限的'申请清单'和'拦截清单'是两回事：按用户要求三件套都申请，
但 31+ 只拦 BLUETOOTH_SCAN/CONNECT——拒绝了定位权限不该把人挡在门外，
那是给 Android 11 及以下扫 BLE 用的。"
```

---

## Task 8: 真机验收

**Files:**
- 不改代码。这一步是拿真板子验证 M1 是否达标，对应 spec §8.7。

**前置**：板子刷着带 BLE 的固件（`cd esp32_170x320` 之后用 arduino-cli 编译上传的那版），滑动菜单切到「蓝牙」页，能看到设备名和 6 位配对码。

- [ ] **Step 1: 出包并拷到手机**

Run: `cd android && /home/bit/tools/gradle-9.7.1/bin/gradle assembleDebug && cp app/build/outputs/apk/debug/app-debug.apk /home/bit/gpcombine-m1.apk`
Expected: `BUILD SUCCESSFUL`，`/home/bit/gpcombine-m1.apk` 存在（约 29 MB）。

- [ ] **Step 2: 逐条走 spec §8.7 的验收标准**

1. 装上 APK → 打开 → 点「扫描设备」→ 列表里出现 `GP-Combine-XXXX` → 点它
2. 输入设备屏幕上的 6 位码 → 进入设备页（不是停在"通信中…"）
3. 设备页显示的版本 / 固件大小 / 卡空间 / RAM / PSRAM **与串口 `[heap]` 日志对得上**
4. 板子断电再上电 → App 重新扫描能再连上
5. `cd android && /home/bit/tools/gradle-9.7.1/bin/gradle :app:testDebugUnitTest` 全绿

- [ ] **Step 3: 对不上时的排查顺序**

按这个顺序查，每一步只看一件事，别跳：

1. **App 连上了但卡在"通信中…"** → 检查是不是没订阅 TX（Task 6 的 CCCD 那步）。固件串口会打 `[ble] SUB tx sub=1`，没这行就是订阅没生效。
2. **`[ble] clients=1` 但没有 `[ble] WR`** → 帧没发出去，查 `send()` 里 MTU 长度检查是不是把帧挡了。
3. **有 `[ble] WR` 但没有 `[ble] rx`** → 字节到了但帧不合法，把 `[ble] WR` 那行和 `Proto.build` 的输出逐字节对比。
4. **有 `[ble] rx` 和 `[ble] SENT` 但 App 没收到** → 问题在 notify 分片重组：MTU 可能只有 23，一个 INFO 回包跨 5 条通知，检查 `FrameParser` 有没有被中途 `reset()`。
5. **版本号/容量显示成 0 或乱码** → `InfoCodec` 的字段顺序问题，见 Task 4 的测试。

- [ ] **Step 4: 记下验收结论并提交**

把实际结果（哪几条过、哪几条没过、串口关键日志）写进 spec §10 的进度段，然后：

```bash
git add docs/superpowers/specs/2026-09-18-phone-app-design.md
git commit -m "docs: M1 控制面真机验收结论"
```

---

## 计划自查

**spec 覆盖**：§8.7 的五条验收标准分别落在 Task 8 的 Step 2；§8.3 的"协议核纯 Kotlin + 与固件共用测试向量"落在 Task 2/3/4；§8.4 的"BleTransport 接口 + FakeTransport"落在 Task 5/6；§8.6 的权限落在 Task 7 的 Step 5；§8.1 的构建约束落在 Global Constraints 和 Task 1。spec 里的 P2（文件传输）、P3（OTA）**不在本计划内**，它们等固件侧 SoftAP + HTTP 做完再单独出计划。

**命名一致性**：`Proto.build/notifyChunk/crc16`、`FrameParser.push`、`Frame(cmd,seq,payload)`、`DeviceClient.ping/auth/info/pairInfo`、`BleTransport.send/inbound/state`、`UiState/Phase` 在各任务之间一致。

**已知取舍**：Task 6 与 Task 7 没有单元测试——Android BLE 需要真机，Compose 页面需要肉眼。它们被刻意做薄（Task 6 只搬字节，Task 7 只做状态展示），所有能出错的逻辑都推到 Task 2–5 那几个有测试的纯 Kotlin 文件里。这是本计划最重要的结构决定，也是为什么 Task 2–5 的测试必须真的跑。
