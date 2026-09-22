# 手机 App 剩余功能实现方案

配合 `2026-09-20-phone-app-feature-list.md` 看：那份说"做什么"，这份说"怎么做"。
**范围**：M1 之后的所有功能。**不含** OTA 和 NES ROM 上传（都归配置助手）。

分期：M2-A 诊断 → M2-B 配置面 → M3 数据面（壁纸）。每期独立可交付、独立验收。

---

## 1. 三条贯穿全局的技术约定

### 1.1 加命令不改帧格式，也不升 `PROTO_VERSION`

帧头 `A5 5A | ver | cmd | seq | len | crc` 不动。新命令只是往命令表里加号，
payload 布局各自定义。`PROTO_VERSION` **只在破坏性改布局时**才 +1——它现在被收帧器严格校验
（收到不认识的 ver 直接当垃圾丢），所以随手跳版本等于让新旧两端互相聋。

命令号空间划分：

| 区间 | 用途 |
|---|---|
| `0x01–0x12` | M1 已有（PING / AUTH / INFO / PAIR_INFO / CFG_*） |
| `0x20–0x3F` | App → 设备的新请求（手柄 / 灯光 / 日志 / WiFi） |
| `0x7F` | 错误帧（已有） |
| `0x80+` | **设备主动推**（不等请求，seq 固定 0） |

`0x80+` 这一段是给"设备主动说话"留的。App 侧 `DeviceClient` 按 seq 配对回包，
不认识 seq 的帧会被忽略——把主动推送放在高位区，将来加请求命令时不会撞进来。

### 1.2 设置只有一份真源：17 字节镜像

固件里 `espCfgPack()` / 回写那一路的 17 字节已经是"ESP32 侧全部设置"的唯一真源，
并且会镜像给 Pico。**App 不再定义第二套字段布局**，一律"读整包 → 改一个字节 → 写整包"：

```
CFG_GET(0x10)  → 17 字节 → App 解析成设置对象
用户改某一项    → App 改对应字节 → CFG_SET(0x11) 整包回写
```

好处：字段增删只改固件一处，App 靠 `p[1]`（镜像格式版本）判断兼容性。Pico 侧的手柄/灯光同理（见 §3.2）。

### 1.3 状态要能被"回显"发现

用户可能直接在设备菜单上改设置，App 不能假设自己是唯一操作者：**进任何设置页先拉一次完整快照**，
不维护"我上次发的就是现在设备上的"这种假设。

---

## 2. M2-A 诊断（先做，后面每期都要靠它）

### 2.1 固件：日志出口

现状：`dbgSink` 是函数指针，把格式化好的短字符串丢给串口（115200，独立于去 Pico 的 UART0）。

改动：

- 新增 `CMD_LOG_SUB (0x06)`：payload 1 字节 —— `0` 关 / `1` 开 / `2` 开且回放最近 N 行
- 新增 `CMD_LOG_EVT (0x86)`：**设备主动推**，payload = `[等级 u8][文本 …]`，seq 固定 0
- `dbgSink` 从"直接写串口"改成"**入队**"：环形缓冲，建议 256 行 × 96 字节
  （放内部 RAM 还是 PSRAM 要看 `[heap]` 实测——内部堆余 249 KB，24 KB 要掂量一下）
- 主循环每 tick 取最多 1 行，`bleLinkSend(0x86, 0, …)` 推给订阅者

**硬约束（spec §4.3）**：`dbgSink` 会被协议栈回调任务调用，**绝不能在回调里直接 notify**，只能入队。
队列满就丢最旧的——日志永远不该阻塞主循环。

诊断帧走的是 `bleLinkSend`，所以它复用现有的 TX 队列和"一次 tick 吐完整帧"的逻辑，不新增机制。

### 2.2 App：三块

1. **日志流页**：LazyColumn + 自动滚动 + 暂停 + 关键字过滤 + 导出（写文件后走系统分享）
2. **帧监视器**：不需要固件配合。UI 上那个 14 行 trace 已经是雏形，扩成结构化记录
   （方向 / 时间 / cmd / seq / payload HEX / 解析结果），做成可展开列表
3. **一键体检**：PING × 20 报 min/avg/max；显示协商到的 MTU；统计一个 INFO 回包分了几片
   （从 trace 数）；内部堆 / PSRAM 定时轮询（2 秒）画曲线

**入口隐藏**：连点"关于"页版本号 5 次才出现。普通用户不需要看见它。

### 2.3 验收

- 手机上看到的日志行与串口一致（同一时刻、同一顺序）
- 日志开着时游戏帧率不掉（NES 42 fps 是基准线）
- 日志流开着时拔掉设备：App 不崩、能重连

---

## 3. M2-B 配置面（不依赖 SoftAP，投入产出比最高）

### 3.1 范围

手柄（映射 / 去抖 / 输入历史 / 按键布局 / **配置档 1–5**）、灯光（灯效 / 颜色 / 亮度 / 速度）、
显示（主题 / 透明度 / 背光 / 翻转 / 反色 / 屏保）、无线蓝牙（nRF 开关 / 重新配对 / 蓝牙开关 /
设备名 / 配对码）。

### 3.2 固件：两类改动

**（a）透传命令**（ESP32 只搬字节，不解析字段）：

| 命令 | 说明 |
|---|---|
| `CMD_GP_GET 0x20` / `CMD_GP_SET 0x21` | payload 原样是 Pico 那条 `0x04 CONFIG` 帧的 payload |
| `CMD_LED_GET 0x22` / `CMD_LED_SET 0x23` | 原样是 `0x06 LED` 的 payload |

好处：不在 ESP32 上再抄一遍字段布局，两边不会漂；底层复用现有 UART 帧机制和 `0x03 STATUS` 回显。

**代价**：App 必须知道这些字段的布局——所以那份布局要变成**共用的机器可读定义**
（导出一个 `layout.json`，App 和固件主机测试都读它，跟帧协议用同一组测试向量是一个思路）。

注意 **改输入模式会让 Pico 自己重启**：ESP32 先告诉 App，App 显示"设备重启中…"，
然后靠已有的重连逻辑等回来。

**（b）配置档 1–5**：`/profiles/1.cfg` … `/profiles/5.cfg`，每份是 17 字节镜像 + 可选名字。
支持"存为档 N"、"加载档 N"、"重命名"。
**顺带把设备菜单那三个死 UI（配置档 / 保存设置 / 恢复默认）补上**——现在定义了但没有任何实现。

### 3.3 App

- 结构：底部 tab（设备 / 手柄 / 灯光 / 显示）+ 设置子页。选底栏而不是深层列表，
  因为设置项只会越加越多，深层列表到第三层就没法用了
- `ConfigViewModel`：持有 17 字节快照 + Pico 设置快照；控件改动 debounce 300ms 后下发；
  维护 `dirty` 标记 + 显式的"保存到设备"（跟设备菜单语义一致，避免每拖一下滑条就写 flash）
- 恢复默认二次确认；「清除配对」明确警告会让所有手机掉线

### 3.4 验收

- App 改的每一项，设备屏幕上立刻看得到（不用退出菜单）
- 设备菜单改的项，App 重新进页面能读到（双向）
- "保存到设备"后断电重启仍然保持
- 配置档 5 份互不串味；加载档 N 后设备当场变化
- 改输入模式触发 Pico 重启时，App 不卡死、能自己等回来

---

## 4. M3 数据面：壁纸（固件要新写 SoftAP + HTTP）

### 4.1 固件

- **SoftAP**：`WiFi.softAP("GP-Combine-XXXX", 8位密码)`，密码随机生成、存 NVS
- **开关走 BLE**：`CMD_WIFI_START (0x30)` 返回 `ssid=…;pass=…;ip=192.168.4.1`；
  `CMD_WIFI_STOP (0x31)` 主动关。60 秒无活动自动关（BLE 连接不受影响）
- **HTTP**：用 Arduino 自带的 `WebServer`，按 spec §6.2 的端点表实现
  （`/api/info`、`/api/list`、`/api/file` 的 GET/PUT/DELETE，PUT 带 `offset` 支持续传）
- **认证**：所有写操作检查 `X-Pair-Code` 头（就是那 6 位配对码），不对返回 401。
  热点本身也必须有密码——不设防的热点等于谁都能刷你的卡
- **写盘**：分片写（≤4 KB/片）+ 主循环让路，屏幕显示进度（沿用现有壁纸写入的做法）。
  传完算 CRC32 比对，不匹配删掉重来，不留半截坏文件
- **传完自动生效**：复用 `gifInit()` 重载
  ⚠️ **开工前必须确认**：`gifLoadFromFs()` 重复调用会不会泄漏 PSRAM（现在的代码没有释放旧缓冲）。
  这是 M3 的第一个必做项，不是"顺手改改"

### 4.2 App：GIF → GFR 转换（纯 Kotlin）

`.gfr` 容器格式（来自 `pc_app/gpfusion_wizard/gif_convert.py`，**逐字段照抄**）：

```
"GFR1" | ver u8(2) | frames u16 | w u16 | h u16 | palsize u8 | datasize u32
       | palette[pal] u16(RGB565) | delays[frames] u16 | offsets[frames] u32 | RLE 数据
```

每帧 RLE：`[len u8][idx u8]` 重复，`len == 0` 表示 256 个。

App 侧步骤：

1. 解码 GIF 多帧：`ImageDecoder`（minSdk 29 够用）逐帧取 Bitmap + 帧延时
2. 缩放：cover / fit / stretch 三种模式（与助手一致）
3. 量化到 16 色索引
4. 每帧 RLE 编码 → 拼 offsets → 写容器

放在 `image/` 包，**不 import `android.*`**（`ImageDecoder` 那步单独隔离成一层），
所以容器写入和 RLE 能在 JVM 上跑单测。

### 4.3 关于「与配置助手输出一致」的定义（要拍板）

spec §8.7 原来写的是"手机转出的 `.gfr` 与 PC 助手输出一致"。**我建议改掉**：

- 助手用的是 PIL 的 LANCZOS 缩放 + 中位切分量化。要在 Kotlin 里逐字节复刻这两套算法，
  成本高，而且 PIL 升个版本就可能漂——等于为了一个没人会去对比的字节级一致性，长期维护两套算法同步
- 固件**只认容器格式，不认是谁生成的**。真正要保证的是"能播 + 好看"

建议改成：

- 硬要求：容器格式合法（固件能读）、尺寸 / 帧数 / 调色板合法、文件大小合理
- 软要求：同一个 GIF 两端各转一次，在设备上播放观感一致（帧数、尺寸、文件大小在 ±20% 内）
- 测试：用助手生成几个 `.gfr` 当**固件侧的测试向量**（固件读文件这条路要测），
  App 侧只测"我生成的文件固件读得懂"

### 4.4 App：上传

- `HttpURLConnection` PUT + `offset` 续传 + 进度 + 取消
- 前台服务 + 通知：切后台不被杀，进度在通知栏
- 连热点：Android 10+ 用 `WifiNetworkSpecifier` 自动连（SSID / 密码从 BLE 拿），
  失败给"手动连接"兜底页（显示 SSID 和密码）
- 手机端给出预计耗时（验收线：2.5 MB / 30 秒）

### 4.5 验收

- 传 2.5 MB 壁纸 30 秒内完成，传完设备当场换壁纸，不重启
- 传一半拔电，重连后从断点续传
- CRC 不匹配时删文件并报错，设备上不出现半截文件
- 传输期间 NES 游戏暂停并有提示，传完恢复

---

## 5. 工程性（摊进各期，不单独排期）

| 项 | 放在哪期 |
|---|---|
| 统一错误文案表（错误码 → 人话） | M2-A（现在每处都是散落字符串） |
| 帧监视器 / trace 结构化 | M2-A |
| 前台服务 + 通知 | M3 |
| 浅色主题 | M2-B（`Theme.kt` 加一套 `lightColorScheme`） |
| 中英文 | 看拍板；要做就在 M2-B 之前把字符串抽进 `strings.xml` |
| 关于页 / 崩溃记录 | M2-A |

---

## 6. 测试策略

| 层 | 怎么测 |
|---|---|
| 纯 Kotlin（帧、GFR 容器、RLE、分片/续传、错误映射） | JVM 单测，继续吃 M1 那套基础设施 |
| 固件纯逻辑（日志环形缓冲、配置档序列化、HTTP offset 解析） | `tools/host_tests`，只 include 真代码、不重写 |
| 协议一致性 | App 与固件共用测试向量（M1 已经在这么做） |
| 真机 | 每期一份验收清单，写在 plan 里 |

**不测的**：Android BLE / HTTP 栈本身、Compose 渲染。靠"逻辑推到可测层 + 真机走一遍"，与 M1 一致。

---

## 7. 顺序与依赖

1. **M2-A 诊断**——无前置。开工会先定"日志队列放内部 RAM 还是 PSRAM"（看 `[heap]` 实测）
2. **M2-B 配置面**——只依赖 BLE + 现有 CFG_GET/SET，可以立刻开工。
   前置：把 Pico 设置字段布局导出成 `layout.json`，否则 App 得靠人肉抄
3. **M3 数据面**——最大的一块（固件 SoftAP + HTTP 从零写）。
   前置：先修 `gifInit()` 重复调用的问题（§4.1）

诊断排在最前，是因为后面每一期的排查都要靠它，早做等于少插几次数据线。

---

## 8. 已拍板（2026-09-22）

1. **`.gfr` 一致性**：同一套压缩 + 格式合法 + 体积不膨胀即可，不要求字节一致
2. **首页结构**：底栏式
3. **日志落盘**：要
4. **浅色主题 / 英文**：不做
5. **NES 只读列表**：不做

---

## 8b. M2-A 任务清单（2026-09-22 开工，当天完工）

状态：**代码全部写完并通过能跑到的检查**；只剩"板子在手上"才能做的那两步（刷机 +
手机上比对日志行）没做——当时板子没插。

已跑过的证据（2026-09-22）：

| 检查 | 命令 | 结果 |
|---|---|---|
| 固件编译 | `arduino-cli compile --fqbn esp32:esp32:esp32s3:PSRAM=opi,FlashSize=16M,PartitionScheme=custom` | 828902 B（4%），RAM 78352 B（23%） |
| 固件纯逻辑主机测试 | `sh tools/host_tests/run.sh` | 全部通过（新增日志队列 29 条断言 + 订阅载荷 8 条） |
| App 单测 | `gradle testDebugUnitTest` | **40/40 通过** |
| App 打包 | `gradle assembleDebug` | `app-debug.apk`，用户自拷安装 |
| 刷机（原生 USB 口 /dev/ttyACM0） | `arduino-cli upload` | ✅ 829114 B，校验通过，板子正常启动 |
| 串口实测（`dbgPrintf` 内容） | 读 /dev/ttyACM0 | ✅ 抓到 `[log] queue ready: 256 lines x 96 bytes (PSRAM)` 等开机行 |
| 手机上比对日志行 | 手机 App 日志页 | **待用户手机测**（本机没有蓝牙适配器，BLE 端到端测不了） |

固件（`esp32_170x320/`）：

- **A1 ✅** `src/net/log_queue.h`：纯头文件环形队列，行宽 96、容量 256，满则丢最旧并计数；
  带 `total()/headSeq()/peekSeq()` 支持"回放最近 N 行"。主机侧可测。
- **A2 ✅** `src/net/proto.h`：加 `CMD_LOG_SUB (0x06)` / `CMD_LOG_EVT (0x86)` + 载荷解析函数。
- **A3 ✅** 固件接线：`dbgPrintf` 同时入队；`CMD_LOG_SUB` 处理订阅（0 关 / 1 开 / 2 开+回放）；
  `netTick` 每圈最多推 1 行；没有手机连着就自动退订。
- **A4 ✅** 队列内存：优先 PSRAM（24 KB），失败退内部堆，再失败就禁用——绝不因为日志把固件搞崩。
  刷机后实测发现"首次订阅才申请内存"会让**第一次**回放窗口是空的（开机那几行永远传不到手机），
  改成 **setup 里就建队列**并打一行 `[log] queue ready: … (PSRAM)`：回放从此真的能拿到开机行。
- **A5 ⏳** 主机测试覆盖队列与订阅载荷（✅）；编译（✅）；刷机 + 串口内容（✅ 见上表）；
  **手机 App 逐行比对待做**。

App（`android_app/`）：

- **A6 ✅** `Proto.kt`：同样两个命令码 + 日志事件解析（`LogCodec`）。
- **A7 ✅** `DeviceClient`：非请求帧（seq 无 pending）分流成 `logs` / `frames` 两条流，别扔。
- **A8 ✅** 帧监视器页：方向 / 时间 / cmd / seq / HEX / 展开看说明与文本。
- **A9 ✅** 一键体检页：PING×20 的 min/avg/max、协商 MTU、INFO 分片数（估算）、
  内部堆与 PSRAM 每 2 秒轮询 + 折线（进页面才开，离开即停）。
- **A10 ✅** UI：底栏（首页 / 配置 / 诊断 / 关于）+ 关于页连点版本号 5 次才出现诊断；
  解锁状态存进 Prefs，重启不用再点。配置页如实写"M2-B 未开工 + 将来搬什么"。
- **A11 ✅** 日志落盘（`filesDir/logs/log-<时间>.log`，一次运行一个文件，只留最近 5 个会话）
  + 导出走系统分享（FileProvider，不需要存储权限）。

### 8b.1 实现期踩到的坑（留给以后）

- `kotlinx-coroutines-test` 的 `advanceUntilIdle()` **不跑 `backgroundScope` 的任务**：
  客户端那侧 collector 一直没订阅上，帧就被 `MutableSharedFlow`（无 replay）直接丢了。
  测试里要先用 `runCurrent()`。真机上没这问题——collector 在连上之前早就订阅好了。
- `LogQueue` 的行宽常量最初叫 `LINE_MAX`，**撞了系统宏**，改了名才编过（现名 `LOG_LINE_MAX`）。
- Material3 的 `NavigationBar` 必须给图标，而这版不想为四个图标拉 `material-icons` 依赖，
  底栏是自绘的（`AppShell.kt` 里的 `BottomBar`）。

---

## 8c. M2-B 任务清单（2026-09-22 拍板后开工）

**拍板**：按键映射**不做进 App**（继续在设备菜单里改）；其余三块全做，外加底栏新开一格「终端」。

分期：

1. **M2-B1 设备/显示/输入/休眠/无线**（本批）—— 覆盖 17 字节配置镜像里的全部项，
   顺手加一条 `0x13 CFG_APPLY`（只应用不落盘），让"改一下立刻生效、点保存才写 flash"成立。
2. **M2-B2 手柄 + 灯光** —— 固件加 `0x20 GP_GET / 0x21 GP_SET / 0x22 LED_GET / 0x23 LED_SET`
   四条透传（载荷就是现有 `0x04 CONFIG` / `0x06 LED` 的原文）。
3. **M2-B3 蓝牙页 + 配置档 1–5** —— 设备名 / 配对码 / 清配对 / `/profiles/N.cfg`，
   顺带补设备菜单那三个死 UI。
4. **不做**：按键映射（Pico 侧完整配置表），要改走设备菜单。

已跑过的检查（2026-09-22）：

| 检查 | 结果 |
|---|---|
| 固件编译 | 829226 B（4%），RAM 78352 B（23%） |
| 固件刷机 + 启动 | ✅ 原生 USB 口刷入校验通过；串口抓到 `[log] queue ready` / `[usb] native port up` / `[dbg] BLE ok` |
| 主机测试 `sh tools/host_tests/run.sh` | 全部通过（新增 `test_esp_cfg`：与 App 同一组向量 + 越界钳制 + 拒收坏镜像） |
| App 单测 `gradle testDebugUnitTest` | **65/65 通过**（新增 EspConfig 7、ConfigController 6、Terminal 12） |
| App 打包 | `app-debug.apk` 30.3 MB |
| 手机端实测设置页/终端 | **未做：本机没有蓝牙适配器，BLE 端到端只能手机测** |

**实现期踩到的坑**：`esp_cfg.h` 的钳制函数第一版返回 `uint8_t`，屏保时间 300 被截成 44——
主机测试当场抓到（`test_esp_cfg` 的 u16 往返断言），所以那组断言是值钱的。

固件：

- **B1 ✅** `src/net/esp_cfg.h`（新）：17 字节镜像的纯函数编解码 + 钳制，无 Arduino 依赖，
  这样主机测试能拿它和 App 对同一组向量。`espCfgPack()/applyEspCfg()` 改成调它。
- **B2 ✅** `esp32_170x320.ino`：新增 `CMD_CFG_APPLY (0x13)` —— 应用 + 重绘，**不**写 flash；
  原 `0x11 CFG_SET` 保持"应用 + 落盘"。
- **B3 ✅** `tools/host_tests/fixes_test.cpp`：`test_esp_cfg()`，向量与 App 侧同一份。

App：

- **B4 ✅** `proto/EspConfig.kt`：17 字段快照 + `toBytes/fromBytes/defaults` + 范围表（和镜像逐字节对齐）。
- **B5 ✅** `net/DeviceClient`：`cfgGet() / cfgApply() / cfgSet() / cfgReset()` + `sendRequest()`（终端用）。
- **B6 ✅** `ble/FakeTransport`：假设备也吃 `0x10/0x11/0x13/0x12` 并存一份快照，
  这样假模式能整套试，`ConfigController` 也能在本机跑测试。
- **B7 ✅** `config/ConfigController.kt`：快照 + `dirty` + 300ms debounce 下发 + 显式保存 + 恢复默认；
  去重用的是"最后一次真正发出去的快照"而不是 dirty，否则"还没读到设备设置"时改动会被静默丢弃。
- **B8 ✅** 单测：`EspConfigTest`（同一份向量 + 越界钳制）、`ConfigControllerTest`（合并下发、
  dirty 语义、reset、未认证时报错、未读也能下发）。
- **B9 ✅** `ui/ConfigScreen.kt`：二级 tab（显示 / 输入 / 休眠 / 无线）+ 控件 + 顶部状态提示 +
  「保存到设备」「恢复默认」（二次确认）。
- **B10 ✅** `term/Terminal.kt`（新）：命令行解析 —— `ping`、`info`、`pair`、`auth <6位>`、
  `logs on|off|replay <n>`、`cfg get|reset`、`cfg set <34位hex>`、`raw <hex>`，以及直接贴裸 hex。
- **B11 ✅** `term/TerminalController.kt`：执行命令 + 输出行。流水不另记一份，
  直接渲染 `DeviceClient.frames`：终端和帧监视器看到的永远是同一件事，回包翻译成人话。
- **B12 ✅** `ui/TerminalScreen.kt`：输入框（回车即发）+ 常用命令快捷按钮 + 输出列表 + 清屏。
- **B13 ✅** 单测：`TerminalTest`（命令解析、hex 解析、未知命令、载荷字节与固件期望一致、
  错误帧变人话、cfg get 翻译成设备菜单里的名字、裸字节不套帧）。
- **B14 ✅** 底栏接入：五格（首页 / 配置 / 终端 / 诊断(隐藏) / 关于）；离开配置页会把
  debounce 里的最后一次改动补发出去。
- **B15 ⏳** 编译 / 刷机 / 主机测试 / App 单测 / 出包 ✅；**手机端逐项验收待做**。

验收（沿用 §3.4）：App 改的项设备屏幕当场可见；设备菜单改的项 App 重新进页面能读到；
「保存到设备」后断电重启仍保持；恢复默认会二次确认。

### 8d. M2-B2 / M2-B3 任务清单（2026-09-22 同日续做）

范围：B2 手柄 + 灯光，B3 蓝牙页 + 配置档 1–5（含补上设备菜单那三个死 UI）。

**协议新增**（`src/net/proto.h` ↔ `proto/Proto.kt` 必须同步）：

| 命令 | 码 | 载荷 |
|---|---|---|
| `GP_GET` / `GP_SET` | `0x20` / `0x21` | 5 字节手柄设置（`pad_cfg.h`） |
| `LED_GET` / `LED_SET` | `0x22` / `0x23` | 7 字节灯光设置 |
| `BT_SET` | `0x25` | 改名 / 改配对码 / 开关（`protoParseBtSet`） |
| `BT_CLEAR` | `0x26` | 让设备随机换码 → 回包带 6 位新码，400ms 后踢掉所有手机 |
| `PROF_LIST` | `0x27` | → 5 × 23 字节定长记录 |
| `PROF_SAVE` / `PROF_LOAD` / `PROF_DEL` / `PROF_RENAME` | `0x28`/`0x29`/`0x2A`/`0x2B` | 存 / 读 / 删 / 只改名 |

蓝牙状态复用已有 `0x04 PAIR_INFO`，只多回报一个 `link=`（0 未启动 / 1 广播中 / 2 已连接）。

**两个刻意的设计选择**（和原计划的措辞不同，理由写在这）：

1. **载荷用"菜单单位"而不是发给 Pico 那两帧的原始字节**。灯光的速度在 Pico 协议里是
   周期时间 u16（`(100-速度)*10+1`），App 上写 92% 不该逼着 App 也做一次这个换算：
   换算只留在固件 `pad_cfg.h` 的 `ledSpeedToCycle/ledCycleToSpeed`，两边的测试向量盯着它。
2. **改配对码后不等 App 手动重连**：设备作废会话前先回包（延迟 400ms 再踢），
   App 拿到新码存进 Prefs 并自动重连认证。不这么做的话"换码"在 App 里就是个死操作。

**固件**：

- `src/net/pad_cfg.h`（新）：手柄 5 字节 / 灯光 7 字节的纯函数编解码 + 钳制 + 速度换算
- `src/net/profiles.h`（新）：`/profiles/N.cfg` 路径、名字清洗（按整字符截到 20 字节）、
  42 字节文件容器（名字 + 17 字节设置镜像）、23 字节列表记录
- `esp32_170x320.ino`：上面 11 条命令的接线；配置档存盘/读盘/删除/改名；
  `sendLedConfig`/`onStatusFrame` 改用 `pad_cfg.h` 的换算；toast 支持自定义文案；
  设备菜单「系统」页补齐：配置档（左右选档）+ 读取配置档 + 存入配置档 + 保存设置 + 恢复默认
- `src/net/ble_link.{h,cpp}`：`bleLinkSetName()` —— 只重启广播，不掉已连的手机
- `cn_font_gen.py` 补了「读取/存入/已读/已存」等字模（240 字），否则 toast 是空白

**App**：

- `proto/PadConfig.kt`（手柄 + 灯光）、`proto/Profiles.kt`、`proto/BtSet.kt`（新）
- `net/DeviceClient`：`padGet/padSet/ledGet/ledSet/btSet/btClear/profiles/profileSave/…`
- `config/PadController.kt`、`LedController.kt`、`BluetoothController.kt`、`ProfileController.kt`（新）
- `ui/ConfigScreen.kt` 改成 `ScrollableTabRow` 八格：显示 / 界面 / 休眠 / 无线 / 手柄 / 灯光 / 蓝牙 / 配置档
- `ui/DeviceTabs.kt`（新）：四个新页（含改名/换码/删档的二次确认）
- `DeviceViewModel`：连上后预读 pad/led/bt；**新增自动重连**（设备主动断线 → 自己连回来
  并用存着的配对码重新认证，3 次不成就让用户回首页）
- 手柄页刻意**不**边改边下发：换输入模式会让 Pico 立刻重启，必须点「应用到设备」

**已跑过的检查（2026-09-22）**：

| 检查 | 结果 |
|---|---|
| 固件编译 | 833050 B（4%），RAM 78448 B（23%） |
| 主机测试 `sh tools/host_tests/run.sh` | 全部通过（新增 `test_pad_cfg` / `test_profiles` / `test_proto_bt_set` / `test_proto_prof_save`） |
| App 单测 | **102/102 通过**（新增 PadConfig 10、Profiles 5、BtSet 4、PadLed 5、BtProfile 12） |
| 测试灵敏度抽查 | 改坏 `PROTO` 的配对码长度 / 假设备的改名实现 → 对应用例当场红，改回即绿 |
| App 打包 | `app-debug.apk` 30.6 MB（`/home/bit/gpcombine-m2b2b3.apk`） |
| 刷机 + 串口 | **未做：板子没插（`/dev/ttyACM0` 不存在）** |
| 手机端实测四页 | **未做：本机无蓝牙适配器** |

**实现期踩到的坑**：

- JUnit 的 `assertNull` 两个参数是 `(消息, 值)`，写反了报的是"拿 ByteArray 当 String"的
  编译错，看不出是参数顺序问题。
- 两次"测试自己写错了"：夹具里 `invertY = 0` 却断言 bit2 置位、配置档列表夹具只填了 3 条
  却断言第 5 条的槽号 —— 都是夹具的锅，实现是对的。
- 手写名字截断必须**按整字符**切（中文一个字 3 字节），按字节硬切会在设备上显示成方块。

---

## 9. 历史：当初需要拍板

1. **`.gfr` 一致性**（§4.3）：我建议从"字节一致"降级成"格式合法 + 观感一致"
2. **首页结构**：底栏 tab 还是列表式（我倾向底栏）
3. **日志要不要落盘**（掉线后还能翻历史）
4. **浅色主题 / 英文**要不要
5. **NES 只读列表**要不要（不做上传）
