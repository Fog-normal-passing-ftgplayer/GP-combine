"""GP-Fusion 配置向导：共享常量与路径。"""
from __future__ import annotations

import os
import platform
from pathlib import Path

APP_NAME = "GP-Fusion 配置向导"
APP_VERSION = "0.5.0"

# ESP32 UI 可选分辨率（准备步骤选择）
SCREEN_RESOLUTIONS: dict[str, tuple[int, int]] = {
    "240x135": (240, 135),     # 默认横屏内容（驱动层旋转到竖屏面板）
    "170x320": (320, 170),     # 1.9寸物理屏 170x320，内容仍为 320x170 横屏
    "172x320": (320, 172),     # 1.47寸物理屏 172x320，内容仍为 320x172 横屏
}
SCREEN_W, SCREEN_H = SCREEN_RESOLUTIONS["240x135"]   # 兼容默认值

# 竖屏变体：工程目录名/ino 名与分辨率字符串同名，NES 小游戏、单数组背景等特性一致
VERTICAL_RES: tuple[str, ...] = ("170x320", "172x320")


def is_vertical(screen_res: str) -> bool:
    """是否为 320×高 的竖屏变体（区别于默认 240x135 横屏工程）。"""
    return str(screen_res or "") in VERTICAL_RES


def screen_dims(screen_res: str) -> tuple[int, int]:
    """按屏幕分辨率字符串返回 (宽, 高)，未知值回退默认。"""
    return SCREEN_RESOLUTIONS.get(str(screen_res or ""), SCREEN_RESOLUTIONS["240x135"])


def background_single_array(size: tuple[int, int]) -> bool:
    """竖屏变体背景只存一张原图，透明度由固件运行时混合（省 flash）。"""
    return size in (
        SCREEN_RESOLUTIONS["170x320"],
        SCREEN_RESOLUTIONS["172x320"],
    )
MENU_BG = (21, 27, 39)                      # esp32.ino 里的 COL_BG
BG_ALPHAS = (0.25, 0.40, 0.55, 0.70, 0.85)  # 5 档透明度，对应机内菜单

FQBN = "esp32:esp32:esp32s3"
# 正式版都跑在 N16R8（16MB flash + 8MB OPI PSRAM）上：
# 自定义分区（app 3MB / LittleFS 12.94MB），需 sketch 目录内 partitions.csv
FQBN_16MB = "esp32:esp32:esp32s3:PSRAM=opi,FlashSize=16M,PartitionScheme=custom"
FQBN_170x320 = FQBN_16MB      # 兼容旧引用


def fqbn_for(screen_res: str) -> str:
    """正式版（240x135 / 170x320 / 172x320）都编译为 N16R8 16MB + OPI PSRAM + 自定义分区。"""
    return FQBN_16MB


def local_build_dir_name(screen_res: str) -> str:
    """本地编译缓存目录名：竖屏变体各自独立，避免 core.a 串用。"""
    return "build_esp32s3_%s" % screen_res if is_vertical(screen_res) else "build_esp32s3"
ESP32_CORE = "esp32:esp32"
ESP32_INDEX_URL = "https://espressif.github.io/arduino-esp32/package_esp32_index.json"

# 默认仓库地址（GP-Fusion 官方仓库）
DEFAULT_REPO_URL = "https://github.com/Fog-normal-passing-ftgplayer/GP-combine.git"


def is_windows() -> bool:
    return platform.system() == "Windows"


def arduino_cli_exe_name() -> str:
    return "arduino-cli.exe" if is_windows() else "arduino-cli"


def default_tool_dir() -> Path:
    if is_windows():
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
        return base / "GPFusion" / "tools"
    return Path.home() / ".gpfusion" / "tools"


def default_source_dir() -> Path:
    """默认克隆目标位置（用户可见的 GPFusion 目录）。"""
    return Path.home() / "GPFusion" / "gp-fusion"


def default_cli_path() -> Path:
    return default_tool_dir() / "arduino-cli" / arduino_cli_exe_name()


def config_dir() -> Path:
    if is_windows():
        base = Path(os.environ.get("APPDATA", str(Path.home())))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return base / "gpfusion"


def state_file() -> Path:
    return config_dir() / "wizard_state.json"


def local_sketch_dir(source_dir: Path, screen_res: str = "240x135") -> Path:
    if is_vertical(screen_res):
        return source_dir / ("esp32_%s" % screen_res)
    return source_dir / "esp32"


def local_sketch_ino(source_dir: Path, screen_res: str = "240x135") -> Path:
    d = local_sketch_dir(source_dir, screen_res)
    if is_vertical(screen_res):
        return d / ("esp32_%s.ino" % screen_res)
    return d / "esp32.ino"


def local_background_header(source_dir: Path, screen_res: str = "240x135") -> Path:
    return local_sketch_dir(source_dir, screen_res) / "background.h"


def local_wallpaper_header(source_dir: Path, screen_res: str = "240x135") -> Path:
    """动态壁纸标记头：存在 = 固件以 GIF 作为主界面动态背景。"""
    return local_sketch_dir(source_dir, screen_res) / "bg_wallpaper.h"


def local_layout_header(source_dir: Path, screen_res: str = "240x135") -> Path:
    return local_sketch_dir(source_dir, screen_res) / "layout_user.h"


def local_wallpaper_gfr(source_dir: Path) -> Path:
    """卡内壁纸文件路径（写入设备 LittleFS 的 /wp/1.gfr）。"""
    return source_dir / "data" / "wp" / "1.gfr"


def local_nes_dir(source_dir: Path) -> Path:
    """卡内 NES ROM 目录（写入设备 LittleFS 的 /nes/*.nes）。"""
    return source_dir / "data" / "nes"


def local_nes_conf(source_dir: Path, screen_res: str = "240x135") -> Path:
    """小游戏运行配置头（缩放模式），仅竖屏版使用。"""
    return local_sketch_dir(source_dir, screen_res) / "nes_conf.h"


def local_defaults_header(source_dir: Path, screen_res: str = "240x135") -> Path:
    return local_sketch_dir(source_dir, screen_res) / "defaults.h"


def local_pico_user_header(source_dir: Path) -> Path:
    return source_dir / "configs" / "GPFusion" / "pico_user.h"


def local_gif_header(source_dir: Path, screen_res: str = "240x135") -> Path:
    return local_sketch_dir(source_dir, screen_res) / "gif_user.h"
