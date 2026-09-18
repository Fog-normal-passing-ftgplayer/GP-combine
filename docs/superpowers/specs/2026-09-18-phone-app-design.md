# GP-Combine 手机 App 设计（BLE 控制面 + WiFi 数据面）

日期：2026-09-18
状态：待评审

## 1. 目标与范围

做一个 Android APK，通过 ESP32-S3 自带的蓝牙连上设备，替代/补充机器上那个 170x320 滑动菜单。

**要做的**

- P1 控制面：BLE 连接 → 改设备全部设置（主题、亮度、翻转、反色、屏保、无线开关、输入历史档位），改完立刻生效并断电保持
- P2 数据面：传文件进设备 LittleFS —— NES ROM（`/nes/*.nes`）、动态壁纸（`/wp/1.gfr`），可列目录、删文件
- P3（可选）：手机升固件（OTA）

**不做的**

- iOS 版（APK 只覆盖 Android；技术选型上留了余地）
- 把 Pico 侧那套网页配置搬进来（Pico 网页配置保持原样，不动）
- 屏幕镜像/实时投屏（BLE 带宽撑不住，WiFi 下也要额外设计）

## 2. 现状与硬约束（实测数据，2026-09-18）

| 项 | 数据 | 来源 |
|---|---|---|
| app 分区占用 | 563,455 B / 4,194,304 B（删掉内嵌 GIF 后） | `arduino-cli compile` |
| 内部 RAM 静态占用 | 284,124 B / 327,680 B，剩 **43,556 B** | 同上 |
| RAM 大头 | `lfb` 108,800 + `rbuf` 108,800（两个整屏缓冲，占静态 77%） | `nm --size-sort` |
| PSRAM | 8 MB，当前代码**一个字节没用** | 全仓库无 `ps_malloc`/`heap_caps_malloc` |
| BLE 开销（核心自带 Bluedroid） | +287 KB flash、+5.7 KB 静态；运行时另需 ~40–60 KB 内部堆 | 对照编译实测 |
| BLE+WiFi+WebServer | +838 KB flash、+26 KB 静态；运行时另需 ~40–50 KB 内部堆 | 对照编译实测 |
| WiFi 缓冲能否用 PSRAM | **不能**（`CONFIG_SPIRAM_TRY_ALLOCATE_WIFI_LWIP` 未开，预编译库定死） | `sdkconfig` |
| 分区表 | `app0` 4 MB @0x10000，`spiffs` 11.94 MB @0x410000，**没有第二个 app 槽** | 设备实读 |
| 蓝牙能力 | ESP32-S3 只有 BLE 5.0，无经典蓝牙 | 芯片规格 |
| 本机工具链 | Java 26、Node 24；**无** Android SDK/Gradle/Kotlin/Flutter | 实测 |

**由此推出的三条结论**

1. 必须先把 `rbuf`（108,800 B）挪到 PSRAM，内部 RAM 才有 ~152 KB 余量装下 BLE+WiFi（否则 43 KB 连 BLE 都紧张）。
2. 传大文件不能走 BLE（实测同类实现 30–80 KB/s，2.5 MB 壁纸要 1 分钟），必须用 WiFi 做数据面。
3. 想要 OTA 必须先动分区表（拆出 `app1`），这一步会重刷分区表，所以放在 P3 并单独确认。

## 3. 总体架构

```
 Android App (Kotlin)
   │  ① 控制面：BLE GATT（常开，几十字节命令）
   │  ② 数据面：WiFi HTTP（按需开启，传完自动关）
   ▼
 ESP32-S3 (GP-Combine 主控)
   │  UART 921600（现有帧协议，不动）
   ▼
 Pico (GP2040-CE 精简版：手柄输入 + 彩灯)
```

- **为什么两条通道**：BLE 省电、免配网、永远在线，适合改参数；WiFi 吞吐高 10–100 倍，适合搬文件。用哪个开哪个，避免 2.4 G 射频共存互相拖慢。
- **为什么 BLE 用 Nordic UART Service（NUS）的 UUID**：手机端可以直接拿 nRF Connect 手敲命令调试，P1 阶段不写 App 就能验证协议全链路，App 只是把同样的帧封进 GATT 写。

## 4. 固件侧设计（ESP32-S3）

### 4.1 新增模块

| 文件 | 职责 |
|---|---|
| `src/net/proto.h` | 帧格式、命令码、错误码（唯一真源，App 侧照抄一份） |
| `src/net/ble_link.cpp/.h` | BLE 服务、广播、连接管理、帧收发、分片组包 |
| `src/net/wifi_link.cpp/.h` | SoftAP 开关、HTTP 服务器、文件读写端点 |
| `src/net/cmd_cfg.cpp` | 设置读写命令实现（复用现有 apply* 函数） |
| `src/net/cmd_fs.cpp` | 文件系统命令实现（列/读/写/删，含断点续传） |
| `src/net/net_tick.cpp` | 主循环里的非阻塞轮询入口 |

### 4.2 与现有代码的接缝

- 设置字段完全复用现有那 17 字节镜像格式（`ok/ver + 16 字节设置`），命令实现直接调用现成的 `applyEspCfg()`/`saveConfigFile()`/`sendEspSave()`，**不新增第二套设置真源**。
- `setup()` 里 `gifInit()` 之后调用 `netInit()`；`loop()` 里每次迭代调用 `netTick()`（非阻塞）。
- 进 NES 游戏时自动停掉 WiFi，避免抢 CPU/PSRAM；BLE 保持广播但拒绝文件类命令。

### 4.3 线程与安全模型（关键）

- BLE 回调（跑在协议栈任务/核 0）**只做一件事：把收到的字节塞进 FreeRTOS 队列**，绝不在回调里写 flash、不做 LittleFS 操作。
- 协议解析、文件读写、设置保存全部在 `netTick()`（主循环，核 1）里做。
- 连接鉴权：设备屏幕显示 6 位码，App 连接后 30 秒内必须发 `AUTH`，否则断开。可以做成开关。

### 4.4 资源占用预算

| 资源 | 现在 | 加完 BLE+WiFi 后 |
|---|---|---|
| Flash（app） | 563 KB | ~1.6 MB（BLE 287 KB + WiFi/HTTP 551 KB + 协议代码） |
| 内部 RAM | 剩 43.5 KB | `rbuf` 挪 PSRAM 后剩 ~152 KB，扣掉 BLE 60 KB + WiFi 50 KB，**余 ~40 KB** |
| PSRAM | ~0 | `rbuf` 108.8 KB + 协议缓冲 8 KB |

## 5. BLE 协议

### 5.1 帧格式（BLE 与 WiFi 共用同一套）

```
偏移  长度  含义
0     2     魔数 0xA5 0x5A
2     1     协议版本 = 1
3     1     命令码
4     2     序号 seq（小端，回包原样带回）
6     2     载荷长度 len（小端，≤ 4096）
8     len   载荷
8+len 2     CRC16-CCITT（覆盖 ver..载荷，小端）
```

BLE 上：`len ≤ MTU-3`，一帧可能跨多个 GATT 写，接收端按 `len` 重组；发送端每 8 片等一个 ACK。

### 5.2 命令表

| 码 | 名称 | 方向 | 载荷 |
|---|---|---|---|
| 0x01 | PING | ↔ | 任意，原样回 |
| 0x02 | AUTH | → | 6 位码（ASCII） |
| 0x03 | INFO | ← | 固件版本、分区、LittleFS 总量/已用、内部 RAM/PSRAM 余量 |
| 0x10 | CFG_GET | ← | `ver + 16 字节设置` |
| 0x11 | CFG_SET | → | `ver + 16 字节设置`，成功后落盘 + 镜像到 Pico |
| 0x12 | CFG_RESET | → | 恢复默认 |
| 0x20 | FS_LIST | ↔ | 请求：路径；回复：`[type, size, name]` 列表 |
| 0x21 | FS_READ | ↔ | 请求：路径 + offset + len；回复：分片数据 |
| 0x22 | FS_WRITE_BEGIN | ↔ | 路径 + 总长 + CRC32；回复：已存在的偏移（续传） |
| 0x23 | FS_WRITE_DATA | → | offset + 数据 |
| 0x24 | FS_WRITE_END | ↔ | CRC32 校验结果 |
| 0x25 | FS_DELETE | → | 路径 |
| 0x30 | WIFI_START | ← | SoftAP SSID + 密码 + IP（BLE 下发给 App） |
| 0x31 | WIFI_STOP | → | 关闭 WiFi |
| 0x40 | OTA_* | （P3） | 需要先有 `app1` 分区 |
| 0x7F | ERR | ← | 错误码 + 文本 |

### 5.3 文件续传

`FS_WRITE_BEGIN` 时若目标文件已存在且长度小于总长，设备返回"已写入字节数"，App 从该偏移继续。每片数据写完后返回已收字节数。传完由 `FS_WRITE_END` 做 CRC32 校验，不匹配就删除文件并报错。

## 6. WiFi 数据面

### 6.1 连接方式：设备开热点（SoftAP），推荐

- SSID：`GP-Combine-XXXX`，密码 8 位随机（App 通过 BLE 的 `WIFI_START` 拿到，用户不用手输）
- 设备 IP：`192.168.4.1`
- 优点：不依赖家里路由器、不需要配网流程、完全离线可用
- 代价：手机连上后 Android 会提示"无互联网连接"，需用户在弹出的对话框里选"仍然连接"（App 里给引导文案）

备选（不推荐）：BLE 下发家里 WiFi 的 SSID/密码，设备连路由。优点是不影响手机上网，代价是要处理 2.4 G only、密码错误、信号弱等一堆失败态。

### 6.2 HTTP 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/info` | 设备信息（同 BLE 的 INFO） |
| GET | `/api/list?path=/nes` | 目录列表（JSON） |
| GET | `/api/file?path=/nes/x.nes` | 下载（支持 Range） |
| PUT | `/api/file?path=/wp/1.gfr&offset=0` | 上传分片，`offset` 支持续传 |
| DELETE | `/api/file?path=...` | 删除 |
| POST | `/api/wifi_stop` | 主动关热点 |

传输期间 60 秒无活动自动关 WiFi；BLE 连接不受影响。

## 7. App 侧设计（Android）

- 技术：**Kotlin + Jetpack Compose**，`minSdk 26`（Android 8.0）、`targetSdk 34`。理由：BLE 是原生 API，不用额外运行时；比 Flutter 少一层依赖。
- 模块划分
  - `ble/`：扫描、连接、MTU 协商、帧编解码、分片重组
  - `http/`：WiFi 上传下载（`HttpURLConnection`/OkHttp 即可，无第三方依赖更好）
  - `ui/`：连接页 → 设备页（信息 + 设置）→ 文件页（壁纸/NES）
  - `store/`：上次设备地址、PIN、主题
- 权限：`BLUETOOTH_SCAN`/`BLUETOOTH_CONNECT`（API 31+）、`ACCESS_FINE_LOCATION`（API 30 及以下扫 BLE 必需）、`INTERNET`
- 断线策略：App 前台自动重连（指数退避），上传中断保留 offset 下次续传

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| BLE 与 WiFi 共用 2.4 G 射频，同开会掉吞吐 | 用哪个开哪个；传文件时 BLE 只保持连接不传数据 |
| 在 BLE 回调里写 flash 会卡协议栈/触发看门狗 | 回调只入队，处理全在主循环 |
| PSRAM 当 SPI DMA 源需要 cache 同步，否则花屏/黑屏 | 挪 `rbuf` 时先单独验证一版：先只挪缓冲、跑 NES 看帧率与画面 |
| 内部 RAM 余量只剩 ~40 KB，协议栈一膨胀就 OOM | 加开机打印内存；把传输缓冲放 PSRAM；必要时改用 NimBLE（省 ~150 KB flash、~20 KB RAM） |
| LittleFS 写 2.5 MB 壁纸耗时，期间菜单会卡 | 分片写（每片 ≤ 4 KB）+ 主循环让路，屏幕显示进度 |
| App 构建要 Android SDK，本机没有 | 优先本地装（一次性 ~1.5 GB，迭代快）；或走 GitHub Actions 出 APK |
| 连 SoftAP 后 Android 判定"无网络" | App 内引导文案 + 手动切回 |

## 9. 分期与验收标准

**P1 控制面（不写 App 也能验证）**

- 固件加 BLE 服务 + 协议 + CFG/INFO 命令；`rbuf` 挪 PSRAM
- 验收：nRF Connect 连上 → `PING` 有回 → `CFG_GET` 拿到 17 字节 → `CFG_SET` 改亮度，屏幕立刻变化；断电重启后保持；NES 帧率不低于改动前（42 fps）
- 交付物：可测固件

**P2 数据面 + App**

- 固件加 SoftAP + HTTP；App 写出来
- 验收：App 连设备 → 传 2.5 MB 壁纸，30 秒内完成且传完自动生效；传 ROM 后设备列表出现并能进游戏；断网重连能续传

**P3 OTA（可选）**

- 改分区表（`app0` 2 MB + `app1` 2 MB，`spiffs` 起点保持 0x410000 不变 → 卡内数据不丢）
- 验收：App 选固件文件 → 设备升级 → 重启后版本号变化

## 10. 待确认（影响实现，需要你拍板）

1. **Android 版本**：按 `minSdk 26` 写行吗？还是要求更老/更新。
2. **传文件走 SoftAP**（手机连设备热点）可以吗？还是你更想设备连家里路由。
3. **Pico 侧的手柄设置和彩灯设置**要不要也搬进 App？现在屏幕上「设置→手柄」「灯光→彩灯」是通过 UART 发给 Pico 的，要做需要额外定义两条命令（多一个阶段的工作量）。
4. **OTA 要不要**（要就得改分区表，且是 P3）。
5. **App 怎么构建**：本地装 Android SDK（推荐，迭代快）还是 GitHub Actions 出 APK 包。
