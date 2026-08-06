# GP-Fusion 配置向导（PC 版）

面向小白的图形化配置工具：引导用户一步步定制自己的 GP-Fusion 固件，
从连接 ESP32-S3、准备编译环境，到选背景图、拖按键布局，最后自动编译上传，
全程不需要碰命令行。

## 功能

1. **连接与准备**
   - 自动检测插入的 ESP32-S3 串口；
   - 自动下载安装 arduino-cli 和 ESP32 核心（esp32:esp32，首次约 300MB）；
   - 自动 `git clone` 你指定的 GP-Fusion 仓库（带进度条），
     也可以选择已有的本地文件夹跳过克隆。
2. **背景图**
   - 选择任意图片，自动转换成屏幕分辨率 240×135；
   - 支持三种缩放方式：裁切填满 / 拉伸填满 / 等比居中；
   - 实时预览 5 档透明度效果，一键生成固件里的 `background.h`。
3. **按键布局**
   - 向导统一生成机内第 4 个「自定义」布局选项；机内前 3 个预设
     （街机 / HITBOX / WASD）保持固件内置不变；
   - **默认布局**：可设置机内上电后默认选中的布局（街机 / HITBOX / WASD /
     自定义），实时写入 `esp32/defaults.h`；
   - 可视化画布：4 个移动键 + 右侧按键 + 可选街机摇杆，所有元素都能直接拖动；
   - 「显示街机摇杆」开关：摇杆捕获 **D-Pad** 方向（非摇杆杆量）；
     开启后自定义布局不再显示移动键（与机内街机预设一致），
     摇杆环与摇杆头可单独编辑位置/半径；
   - **自定义文字**：每个按键的文字（最多 4 个字符）都可以改；
   - 圆形/方形切换、半径/边长调节、摇杆环半径与摇杆头调节；
   - **添加按键**：可额外映射 L3 / R3 / S1 / S2 / A1 / A2 / A3 / A4，
     添加后可拖动位置、调整大小，也可删除；
   - **任意按键都可删除**（移动键/右侧键/摇杆，摇杆删除即隐藏）；
   - 所有修改实时写入 `esp32/layout_user.h`。
4. **编译上传**
   - 一键编译固件并上传到 ESP32-S3，实时日志输出；
   - 上传完成后固件即生效。

## 运行（开发）

需要 Python 3.10+：

```bash
cd pc_app
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

自检（无界面）：`python main.py --smoke`

## 打包

Linux：`./build_linux.sh`，输出在 `dist/GPFusionWizard/`。

Windows：双击 `build_windows.bat`（自动建虚拟环境、装依赖、打包并生成 zip），
输出在 `dist\GPFusionWizard\`，压缩包为 `dist\GPFusionWizard-windows.zip`。
需要先装 64 位 Python 3.10+ 并勾选 "Add python.exe to PATH"。
如果程序无法启动，把 `dist\GPFusionWizard\gpfusion_crash.log` 发给开发者即可定位。

打包机建议在对应平台上执行；PyInstaller 不支持跨平台打包。

## 使用流程

1. 用 USB 插入 ESP32-S3（普通模式即可，不需要手动进下载模式）。
2. 软件检测到设备后会自动开始准备工具链；仓库地址请填写
   **你 fork 的、包含 `esp32/esp32.ino` 的 GP-Fusion 仓库地址**。
   已有源码的可以直接点“选择已有文件夹”。
3. 选背景图 → 生成。
4. 拖布局 → 自动写入源码。
5. 点“开始上传”，等待编译上传完成。

## 常见问题

- **克隆完成后提示“仓库中没有 esp32/esp32.ino”**：上游 GP2040-CE 仓库不含
  ESP32 固件目录，必须使用包含 `esp32/` 的 GP-Fusion fork 地址，或用
  “选择已有文件夹”直接指定。
- **arduino-cli 下载慢/失败**：可手动下载对应平台的 arduino-cli 放到
  `~/.gpfusion/tools/arduino-cli/`（Windows 为
  `%LOCALAPPDATA%\GPFusion\tools\arduino-cli\`），软件会自动识别。
- **ESP32-S3 检测不到**：检查 USB 线是否为数据线；Windows 首次使用原生
  USB 串口无需驱动，外接 CP210x 转串口需装驱动。
- **上传失败**：确认设备仍在线、没有别的串口工具占用该端口。

## 目录结构

```
pc_app/
  main.py                    入口
  gpfusion_wizard/
    app_config.py            常量与路径
    serial_detect.py         ESP32-S3 串口检测
    toolchain.py             arduino-cli / ESP32 核心 / git
    jobs.py                  后台任务与进度解析
    imagegen.py              背景图转换与 background.h 生成
    layout_model.py          按键布局数据模型
    layout_header.py         layout_user.h 生成
    uploader.py              编译/上传命令
    wizard_state.py          状态持久化
    ui/                      向导界面
  gpfusion.spec              PyInstaller 配置
  build_linux.sh / build_windows.bat
```
