# UI 仿真器（宿主机跑固件渲染层）

把 `esp32/` 和 `esp32_170x320/` 的**屏幕界面搬到电脑上跑**，用来截取菜单、出展示图、做动画素材，或者单纯调 UI 不用每次刷机。

产物是**真机的真实画面**，不是重绘：同一份 `.ino` 源码，同一套菜单状态机，同一套字体与布局代码。

---

## 为什么能做到「零改动」

`.ino` 文件在 Arduino 下有几个宿主机 g++ 不接受的特性，最要命的是**函数可以先用后定义**。所以这个工具不直接编 `.ino`，而是：

```
arduino-cli compile
      ↓  生成 sketch/<名字>.ino.cpp（已插入自动函数原型）
宿主机 g++ 编译这一份 .cpp + 平台垫片
      ↓
仿真器可执行文件
```

结论：**`.ino` 源码一行都不用改**，仿真器吃的是 arduino-cli 的真实预处理产物。固件改了，重跑一次 `build.sh` 就同步。

---

## 依赖

| 依赖 | 用途 |
|---|---|
| `arduino-cli` + esp32 core | 生成带原型的 `.ino.cpp`（只在首次、或固件改动后需要） |
| `g++`（支持 C++17） | 编仿真器 |
| `libX11` | 图形窗口 |
| `zlib` | 写 PNG |
| `python3` | `make_tour.py` 生成巡演脚本 |

Arch / CachyOS：

```bash
sudo pacman -S arduino-cli gcc libx11 zlib python
```

Debian / Ubuntu：

```bash
sudo apt install g++ libx11-dev zlib1g-dev python3
```

`arduino-cli` 还要装 esp32 支持包：

```bash
arduino-cli core install esp32:esp32
```

---

## 快速开始

```bash
cd tools/ui_sim

# 1) 编（首次会自动调 arduino-cli，几分钟）
./build.sh            # 240x135
./build.sh 320        # 170x320

# 2) 跑：开一个可交互窗口
./run.sh              # 240x135
./run.sh 320          # 170x320
./run.sh 320 --scale=3 --fps=60
```

窗口里的按键（用电脑键盘模拟手柄）：

| 键 | 对应 |
|---|---|
| `↑ ↓ ← →` | 十字键 |
| `1` | S2（**长按 3 秒进菜单**） |
| `2` | S1 |
| `z` | A（确认 / 进子页） |
| `x` | B（返回） |
| `Esc` | 退出 |

> 窗口需要**先点一下**才有键盘焦点（仿真器用 `XQueryKeymap` 读真实按下/抬起，
> 终端拿不到按键抬起事件，所以只能走 X11）。

---

## 五种运行模式

| 模式 | 说明 |
|---|---|
| `--mode=keys` | 交互窗口，默认。也可以用 `--no-window` 不开窗 |
| `--mode=tour` | **按脚本回放并定点截图**，出素材用这个 |
| `--mode=wallpaper` | 从主界面开始，把壁纸动画的每一帧变化导出成 `w000.png…` |
| `--mode=script` | 内置的演示脚本（旧，保留兼容） |
| `--mode=idle` | 不喂输入，只跑主循环，用于看开机动画/屏保 |

常用参数：

```
--out=DIR        输出目录（默认 out）
--scale=N        窗口放大整数倍
--fps=N          窗口刷新率
--step=us        仿真步长（微秒；1000 = 1ms）
--fs=DIR         把设备上的 LittleFS 根映射到本地目录
                 （例如 --fs=../../data 就能读到 data/wp/1.gfr 壁纸）
--count=N        wallpaper 模式导出的帧数上限
```

---

## 巡演脚本（出截图的标准做法）

`--mode=tour --script=tours/320.tour` 会按脚本喂按键，并在指定时刻存图。

脚本文本是纯文本，一行一条：

```
hold <起始ms> <结束ms> <按键...>     # 按住某键；'-' 表示无输入
shot <文件名> <时刻ms>                # 到点存一张 <out>/<文件名>.png
end  <结束ms>                         # 不写则自动推到最后一个时刻 +500ms
# 井号开头是注释
```

按键名：`up` `down` `left` `right` `a` `b` `s1` `s2`。

### 手写还是生成？

`tours/240.tour`、`tours/320.tour` 是 **`make_tour.py` 生成的**，不建议手写：

```bash
python3 make_tour.py 240 tours/240.tour
python3 make_tour.py 320 tours/320.tour
./run.sh 320 --mode=tour --script=tours/320.tour --out=shots/320 --step=8
```

原因：每步按键都要等动画（翻页 280ms、列表 140ms），而且**从子页按 B 返回会把菜单游标重置到第 0 页**，手算时间点几乎必错。生成器里把这些时序都参数化了，直接改常量即可。

### 加一个新页面

1. 固件里加页面（`PAGE_TITLES` / `subDefs` / `*Sections`）
2. 改 `make_tour.py` 里的 `pages` 列表，加一条 `(页号, 文件名, 类型)`
3. 重跑上面两条命令

---

## 出动画素材（展示站用）

壁纸动画是 60 帧循环，逐帧导出再编码：

```bash
# 1) 导出壁纸的每一帧（只在画面变化时存）
./run.sh 320 --mode=wallpaper --out=wp320 --count=60 --fs=../../data

# 2) 编码成动画 WebP
#    帧时长直接取自 .gfr（真机就是这个节奏），不要凭空设帧率
ffmpeg -framerate 20 -i wp320/w%03d.png -loop 0 \
       -c:v libwebp -lossless 1 wallpaper.webp
```

> **无损反而更小**：壁纸是 16/32 色调色板内容，WebP 无损比 `q:v 80` 更小
> （实测 794KB vs 983KB），而且像素画不会有压缩伪影。

翻页动画则是录 `tours/slide_page.tour` 的帧（`--frames` 会存每个变化的帧），
再按 60fps 编码，末尾补一段静止帧便于循环观看。

---

## 与配置助手集成（真机画面预览）

配置助手的「GIF 动画」页右侧显示的是**固件本体渲染的真实画面**，不是把 GIF 缩放给你看——
状态栏、按键布局、主题、壁纸叠加都是真机那份代码画出来的。

链路：助手转码 `.gfr` → 调仿真器的 headless 构建导出帧 → 按 `.gfr` 的帧延迟在控件里循环播放。

### 构建 headless 版（不依赖 X11）

```bash
HEADLESS=1 ./build.sh 240    # -> build/sim240
HEADLESS=1 ./build.sh 320    # -> build/sim320
```

headless 版没有图形后端（`-DSIM_HEADLESS`），`--mode=keys` 会明确拒绝；
其余模式（`tour` / `wallpaper` / `idle`）照常工作。产物不链接 libX11。

助手通过 `firmware_preview.find_sim()` 自动找，优先级：

1. 环境变量 `GPFUSION_SIM_240` / `GPFUSION_SIM_320`
2. 打包内 `gpfusion_wizard/bin/sim240|sim320`
3. 仓库 `tools/*/build/sim240|sim320`（开发态）

### 助手等价于这样调用

```bash
./build/sim320 --mode=wallpaper --out=/tmp/frames --count=60 --fs=/tmp/gpv_xxx
```

`--fs` 目录下放：

```
wp/1.gfr         壁纸本体（助手从 GIF 转码而来）
gpfusion.cfg     可选，纯文本 key=value，用来预设菜单项
```

`gpfusion.cfg` 支持的键（与固件 `loadConfigFile()` 一致）：
`layout` `theme` `style` `bg_level` `bl` `hflip` `vflip` `inv`
`hist` `saver` `saver_ms` `screenoff` `wl`。

有了它，预览就能反映用户在助手里选的配置，而不是永远显示固件默认值。

## 平台垫片（`shim/`）覆盖了什么

| 文件 | 垫掉的东西 |
|---|---|
| `Arduino.h` | `String` / `File`（含 `opendir` 目录遍历，NES ROM 列表要用）/ `SimSerial` / `ps_malloc` / `ledcWrite` 等，`SET_LOOP_TASK_STACK_SIZE` 空宏 |
| `SPI.h` | `SPIClass`；`transfer()` 固定返回 `0x20`（TX_DS），否则 nRF24 的发送等待会死循环 |
| `LittleFS.h` | 把设备路径映射到本地目录，`--fs=` 指根 |
| `freertos/*` | 真实环形缓冲队列 + `xTaskCreatePinnedToCore` 等桩 |
| `driver/spi_master.h` | ESP-IDF 的 DMA 推屏 API（`spi_bus_initialize` / `spi_device_queue_trans`…） |
| `esp_heap_caps.h` | `heap_caps_malloc(..., MALLOC_CAP_SPIRAM)` → 普通堆 |

---

## 已知限制与踩坑记录

**时间源是假的，但完全确定** —— 仿真器用 `g_us` 单一假时钟，不用 `gettimeofday`。
所以同一份巡演脚本每次跑出来的帧完全一致，适合比对回归。窗口模式下会同步到真实时间。

**`--step` 单位是微秒**，不是毫秒。`--step=8` 实际是 8µs → 被钳到 1ms，不是 8ms。

**列表滚动动画不是 16ms 节拍** —— 固件的 `updateListAnim()` 每轮主循环都重绘，
140ms 的动画会产出约 140 个不同帧。要录它必须先降采样到 60fps。

**`Xlib.h` 必须在固件源码之后 include** —— 它会 `#define None/Bool/Status`，
提前引入会把固件里的同名标识符全搞坏。

**`pkill -f sim_xxx` 会匹配到自己** —— 进程名超过 15 字符会被内核截断，
`pkill -x` 也匹配不上，用 `pidof` 拿 PID 再 `kill`。

**壁纸来源** —— 两个变体现在**都只从卡内 `/wp/1.gfr` 读取**（配置助手生成），
所以要用 `--fs=../../data` 才会动。不带 `--fs` 时表现就是"没装壁纸"：
静态背景 + 屏保正常工作。

`.gfr` 的分辨率必须和屏幕一致，否则会被拒绝并在背景页提示
「壁纸分辨率不符（需 WxH）」—— 这是故意的，防止把 170x320 的壁纸丢进 240x135 的机器。

**动态壁纸不再需要编译开关** —— 以前要 `bg_wallpaper.h`（配 `__has_include`）
才能把壁纸代码编进去，忘了生成就完全没有壁纸，很难查。现在改成**运行时判断**：
卡里有合法 `.gfr` 就启用（屏保禁用、休眠页「屏保模式」锁定），没有就退回静态背景。
两个变体的行为完全一致，换壁纸也不用重刷固件。

---

## 目录结构

```
tools/ui_sim/
├── README.md          本文件
├── build.sh           编仿真器（首次会调 arduino-cli）
├── run.sh             运行
├── sim_main.cpp       仿真器本体：平台实现、PNG 输出、X11 窗口、按键注入、巡演回放
├── make_tour.py       生成巡演脚本（推荐方式）
├── tours/             巡演脚本：240 / 320 各一份，另有两条抓动画用的
├── shim/              平台垫片（见上表）
└── build/             构建产物，已 gitignore
```

---

## 它产出过什么

`https://fog-normal-passing-ftgplayer.github.io/` 上的全部截图与动画，
都是从这套工具出来的：7 个菜单页面、每页的选项列表、翻页动画、动态壁纸循环。
