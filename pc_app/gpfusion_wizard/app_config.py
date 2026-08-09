"""GP-Fusion 配置向导：共享常量与路径。"""
from __future__ import annotations

import os
import platform
from pathlib import Path

APP_NAME = "GP-Fusion 配置向导"
APP_VERSION = "0.2.0"

# ESP32 UI 内容分辨率（横向 240x135，驱动层再旋转到竖屏面板）
SCREEN_W = 240
SCREEN_H = 135
MENU_BG = (21, 27, 39)                      # esp32.ino 里的 COL_BG
BG_ALPHAS = (0.25, 0.40, 0.55, 0.70, 0.85)  # 5 档透明度，对应机内菜单

FQBN = "esp32:esp32:esp32s3"
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


def local_sketch_dir(source_dir: Path) -> Path:
    return source_dir / "esp32"


def local_sketch_ino(source_dir: Path) -> Path:
    return local_sketch_dir(source_dir) / "esp32.ino"


def local_background_header(source_dir: Path) -> Path:
    return local_sketch_dir(source_dir) / "background.h"


def local_layout_header(source_dir: Path) -> Path:
    return local_sketch_dir(source_dir) / "layout_user.h"


def local_defaults_header(source_dir: Path) -> Path:
    return local_sketch_dir(source_dir) / "defaults.h"


def local_pico_user_header(source_dir: Path) -> Path:
    return source_dir / "configs" / "GPFusion" / "pico_user.h"


def local_gif_header(source_dir: Path) -> Path:
    return local_sketch_dir(source_dir) / "gif_user.h"
