# UI 仿真器（Windows 宿主机跑固件渲染层）

把 `esp32/`（240×135）、`esp32_170x320/`（320×170）、`esp32_172x320/`（320×172）的
**屏幕界面搬到电脑上跑**，用来截取菜单、出展示图、做动画素材，或者调 UI 不用每次刷机。

产物是**真机的真实画面**，不是重绘：同一份 `.ino` 源码，同一套菜单状态机，同一套字体与布局代码。
本目录是 Linux 版（X11 + zlib + g++）的 Windows 原生移植，**业务帧协议、CLI 参数、tour 脚本格式与 Linux 版完全一致**，不改固件 UI 逻辑。

---

## 为什么能做到「零改动」

`.ino` 在 Arduino 下有几个宿主机编译器不接受的特性，最要命的是**函数可以先用后定义**。所以工具不直接编 `.ino`，而是：

```
arduino-cli compile
      ↓  生成 sketch/<名字>.ino.cpp（已插入自动函数原型）
宿主机 MSVC 编译这一份 .cpp + 平台垫片
      ↓
仿真器 exe
```

结论：**`.ino` 源码一行都不用改**，仿真器吃的是 arduino-cli 的真实预处理产物。固件改了，重跑一次 `build.bat` 就同步。

---

## 依赖

| 依赖 | 用途 |
|---|---|
| Visual Studio Build Tools（MSVC C++ 桌面开发，x64） | 编仿真器本体 |
| Windows 10/11 SDK | Win32 / GDI+ 头与库 |
| `arduino-cli` + esp32 core（3.3.12） | 生成带原型的 `.ino.cpp`（只在首次、或固件改动后需要） |
| Python 3 | `make_tour.py` 生成巡演脚本 |

> 不需要 MinGW、WSL、libX11 或 zlib：窗口走 Win32，存 PNG 走系统自带的 GDI+。

arduino-cli 装 esp32 支持包：

```
arduino-cli core install esp32:esp32
```

---

## 快速开始

双击或在命令行运行：

```bat
build.bat            :: 240x135（esp32）
build.bat 320        :: 170x320（esp32_170x320）
build.bat 172        :: 172x320（esp32_172x320）

run.bat              :: 240x135 交互窗口
run.bat 320          :: 170x320
run.bat 172          :: 172x320
run.bat 320 --scale=3 --fps=60
```

### 分两步：生成 `.ino.cpp`（慢）和编仿真器（快）

```bat
compile_ino.bat          :: 三个变体都生成（arduino-cli，几分钟）
compile_ino.bat 320      :: 只生成 170x320

build.bat                :: 编 exe（几秒；不再碰 ESP32 工具链）
build.bat --check        :: 只检查工具链，别编译
```

**为什么拆开**：arduino-cli 要跑 ESP32 工具链（几分钟），编仿真器只要几秒。
合在一起的话改一行仿真器代码也要等工具链，而且 `.ino.cpp` 没用上最新固件时
会静默跑旧代码、很难发现。

`build.bat` 现在只做检查：`.ino.cpp` 缺失、或**源码内容哈希**变了（存在
`build/<名字>/.ino_src_hash`），就报错让你先跑 `compile_ino.bat`。
加 `set AUTO_INO=1` 可恢复"自动编译"的旧行为。

> 用内容哈希而不是修改时间：arduino-cli 有增量缓存，源码没实质变化时不会
> 重写产物，靠时间戳判断会一直误报过期。

### 工具链

优先用 **Visual Studio 2019/2022**（「使用 C++ 的桌面开发」）——脚本通过
`vswhere -find` 找到真正的 `vcvars64.bat`，不写死版本号，也不需要手工拼
Windows SDK 的 include/lib（`vcvars64` 自己会配好）。

没有 VS 时退化为 **PATH 上的 MinGW-w64 g++**（会把 exe 静态链接，单文件可分发）。
`build.bat --check` 会打印当前识别到的工具链。

窗口里的按键（电脑键盘模拟手柄）：

| 键 | 对应 |
|---|---|
| `↑ ↓ ← →` | 十字键 |
| `1` | S2（**长按 3 秒进菜单**） |
| `2` | S1 |
| `z` | A（确认 / 进子页） |
| `x` | B（返回） |
| `Esc` | 退出 |

> 窗口需要**先点一下**才有键盘焦点（仿真器用 `GetAsyncKeyState` 读真实按下/抬起）。

---

## 五种运行模式

| 模式 | 说明 |
|---|---|
| `--mode=keys` | 交互窗口，默认。也可以用 `--no-window` 不开窗（退化为控制台按键） |
| `--mode=tour` | **按脚本回放并定点截图**，出素材用这个 |
| `--mode=wallpaper` | 从主界面开始，把壁纸动画的每一帧变化导出成 `w000.png…` |
| `--mode=script` | 内置演示脚本（旧，保留兼容） |
| `--mode=idle` | 不喂输入，只跑主循环，用于看开机动画/屏保 |

常用参数（与 Linux 版一致）：

```
--out=DIR        输出目录（默认 out）
--scale=N        窗口放大整数倍
--fps=N          窗口刷新率
--step=us        仿真步长（微秒；1000 = 1ms）
--fs=DIR         把设备 LittleFS 根映射到本地目录
                 （例如 --fs=..\..\data 读 data\wp\1.gfr 壁纸）
--count=N        wallpaper 模式导出帧数上限
--no-window      不开图形窗口
--script=FILE    tour 脚本
--frames         导出每个变化的帧
```

---

## 巡演脚本（出截图的标准做法）

`--mode=tour --script=tours\320.tour` 按脚本喂按键，到点存图。纯文本，一行一条：

```
hold <起始ms> <结束ms> <按键...>     # 按住某键；'-' 表示无输入
shot <文件名> <时刻ms>                # 到点存一张 <out>/<文件名>.png
end  <结束ms>                         # 不写则自动推到最后时刻 +500ms
# 井号开头是注释
```

按键名：`up` `down` `left` `right` `a` `b` `s1` `s2`。

`tours\240.tour`、`tours\320.tour`、`tours\172.tour` 由 `make_tour.py` 生成，不建议手写：

```bat
python make_tour.py 240 tours\240.tour
python make_tour.py 320 tours\320.tour
python make_tour.py 172 tours\172.tour
run.bat 320 --mode=tour --script=tours\320.tour --out=shots\320 --step=8
```

原因：每步按键都要等动画（翻页 280ms、列表 140ms），而且**从子页按 B 返回会把菜单游标重置到第 0 页**，手算时间点几乎必错。生成器把这些时序参数化了，直接改常量即可。

### 加一个新页面

1. 固件里加页面（`PAGE_TITLES` / `subDefs` / `*Sections`）
2. 改 `make_tour.py` 里的 `pages` 列表，加一条 `(页号, 文件名, 类型)`
3. 重跑上面两条命令

---

## 平台垫片（`shim/`）覆盖了什么

| 文件 | 垫掉的东西 |
|---|---|
| `Arduino.h` | `String` / `File`（含目录遍历，NES ROM 列表要用）/ `Serial` / `ledcWrite` 等；MSVC 下 `strcasecmp`→`_stricmp`、空 `__attribute__` 宏 |
| `SPI.h` | `SPIClass`；`transfer()` 固定返回 `0x20`（TX_DS），否则 nRF24 发送等待会死循环 |
| `LittleFS.h` | 设备路径映射到本地目录，`--fs=` 指根 |
| `freertos/*` | 环形缓冲队列 + `xTaskCreatePinnedToCore` 等桩 |
| `driver/spi_master.h` | ESP-IDF 的 DMA 推屏 API |
| `esp_heap_caps.h` | `heap_caps_malloc(..., MALLOC_CAP_SPIRAM)` → 普通堆 |

---

## 已知限制与踩坑记录

**时间源是假的，但完全确定** —— 仿真器用 `g_us` 单一假时钟，不用系统时钟。同一份巡演脚本每次跑出来的帧完全一致，适合回归比对。窗口模式下同步到真实时间。

**`--step` 单位是微秒**，不是毫秒。`--step=8` 是 8µs → 被钳到 1ms，不是 8ms。

**目录句柄空值判定** —— Windows 下 `INVALID_HANDLE_VALUE` 是 -1，默认 File 的目录句柄是 `nullptr`；两者都要判空，否则不存在的目录会被当成有效目录，`FindNextFile` 直接访问违例。

**源码含中文注释/字串** —— cl 必须带 `/utf-8`，否则 GBK 误读会吃掉换行、报一堆莫名其妙的 `#endif` 错误。

**Win32/GDI+ 头要在固件之前 include** —— 固件 `Arduino.h` 会 `#define INPUT/OUTPUT` 等宏，先引固件再引 `windows.h` 会把 `winuser.h` 里的 `INPUT` 结构体名冲掉。

**GDI+ 存 PNG 的路径转换** —— argv 经 CRT 按系统 ANSI 码页（中文系统为 GBK）传入，写文件前用 `MultiByteToWideChar(CP_ACP, …)` 转 UTF-16；逐字节扩成 `wchar_t` 会在中文路径下存不下图。

**arduino-cli 只用来出 `.ino.cpp`** —— 跨架构链接（xtensa ld）在含中文的路径下可能写不出 `.elf`，这一步失败不影响本机仿真：仿真只需要它生成的 `sketch\*.ino.cpp`。固件烧录仍在 Arduino IDE 里做。

**172 的 `lfb` 是指针** —— 与 170 的数组不同，172 在 `setup()` 里 `heap_caps_malloc` 分配；`writePng`/`hashLfb` 都有空指针守卫，未分配时不会解引用。

**壁纸来源** —— `esp32_170x320/`、`esp32_172x320/` 没有内嵌 `gif_user.h`，壁纸只能来自卡内 `/wp/1.gfr`，要带 `--fs=..\..\data`；`esp32/` 有内嵌版，不带 `--fs` 也能动。

**动态壁纸需要 `bg_wallpaper.h`** —— 固件用 `__has_include` 探测，没有这个头 `WALLPAPER_ACTIVE` 就是 0，整条壁纸代码不参与编译。配置助手正常会生成它。

---

## 目录结构

```
GP-combine固件彩屏模拟（windows版本）/
├── README.md          本文件
├── build.bat          编仿真器（首次调 arduino-cli）
├── run.bat            运行
├── sim_main.cpp       仿真器本体：平台实现、GDI+ PNG、Win32 窗口、按键注入、巡演回放
├── make_tour.py       生成巡演脚本（推荐方式）
├── tours/             巡演脚本：240 / 320 / 172，另有两条抓动画用的
├── shim/              平台垫片（见上表）
└── build/             构建产物，已 gitignore
```

---

## 它产出过什么

`https://fog-normal-passing-ftgplayer.github.io/` 上的全部截图与动画，都来自这套工具：菜单页面、选项列表、翻页动画、动态壁纸循环。Windows 版与 Linux 版出的是同一套固件画面。