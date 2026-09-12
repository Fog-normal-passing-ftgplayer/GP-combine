# GP-Combine 懒人版配置助手（pcapp_dumbversion）

给小白用的**离线版**配置助手：不用装 Python、不用装 Arduino、不用科学上网，
打开就能改背景 / 壁纸 / 按键布局 / 小游戏 ROM，然后一键编译并刷进 ESP32。

## 懒人包目录约定

```
GP-Combine-懒人包/
├─ Start-GP-Combine.exe / start-linux.sh   ← 启动器
├─ app/pcapp_dumbversion/                  ← 本程序
├─ tools/
│   ├─ arduino-cli/arduino-cli             ← 必需
│   └─ pico-sdk/                           ← 可选（完整版才有）
├─ arduino-data/                           ← ARDUINO_DIRECTORIES_DATA
│   └─ packages/esp32/{hardware,tools}/    ← 内置 esp32 core + 工具链
├─ arduino-user/                           ← ARDUINO_DIRECTORIES_USER
├─ src/GP-Combine/                         ← 源码快照（含 esp32/、esp32_170x320/）
├─ firmware/                               ← 预编译固件（可选，走「刷预编译固件」）
└─ work/                                   ← 运行期生成（构建产物、卡内文件镜像、状态）
```

程序靠 `arduino-data/` 这个目录判断自己是不是在懒人包里：

* **在包里**：只用包内 arduino-cli / core，全程离线；状态文件写 `work/dumb_state.json`
* **不在包里**（开发模式）：退回到仓库根 + `~/.arduino15`，方便在开发机上改代码调试

## 怎么用

```bash
./start-linux.sh                 # 或者 python3 main.py
python3 main.py --selftest       # 不开界面，只检查包是否完整
python3 main.py --bundle /path/to/包根
```

界面就三块：**想要什么**（分辨率 / 背景 / 布局 / ROM）、**干活**（一键编译刷入、只编译、
写入卡内文件、整机重刷、刷预编译固件）、**日志**。

## 生成懒人包

用仓库里的脚本一键打包（会装/复用 esp32 core、复制源码、可选编译预编译固件）：

```bash
python3 tools/make_bundle.py --out dist/GP-Combine-lazy --zip
python3 tools/make_bundle.py --out dist/... --from-data ~/.arduino15   # 复用本机已装好的 core
python3 tools/make_bundle.py --out dist/... --link-core ~/.arduino15   # 开发用：core 用软链接，不复制
python3 tools/make_bundle.py --out dist/... --prebuilt                 # 顺带编译两版预编译固件
```

## 高级功能放哪

自定义布局编辑、Lite（Pico i2c）版本、网页配置、备份导入导出这些在**完整版配置助手**
（仓库 `pc_app/`）里；懒人版刻意不塞，避免小白点错。
