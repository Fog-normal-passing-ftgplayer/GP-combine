"""工具链检测与命令构造：arduino-cli、ESP32 核心、git。"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .app_config import (
    ESP32_CORE,
    ESP32_INDEX_URL,
    arduino_cli_download_url,
    arduino_cli_exe_name,
    default_cli_path,
)


def find_arduino_cli() -> Path | None:
    """优先用户默认工具目录，其次系统 PATH。"""
    default = default_cli_path()
    if default.is_file():
        return default
    found = shutil.which("arduino-cli")
    if found:
        return Path(found)
    return None


def git_available() -> bool:
    try:
        out = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return out.returncode == 0
    except Exception:
        return False


def core_installed(cli: Path) -> bool:
    try:
        out = subprocess.run(
            [str(cli), "core", "list"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return out.returncode == 0 and ESP32_CORE in out.stdout
    except Exception:
        return False


def cli_version(cli: Path) -> str:
    try:
        out = subprocess.run(
            [str(cli), "version"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        return (out.stdout or out.stderr).strip().splitlines()[0][:60] if out.returncode == 0 else ""
    except Exception:
        return ""


# ---------- 命令构造 ----------

def config_init_cmd(cli: Path) -> list[str]:
    return [str(cli), "config", "init"]


def add_index_cmd(cli: Path) -> list[str]:
    return [str(cli), "config", "add", "board_manager.additional_urls", ESP32_INDEX_URL]


def update_index_cmd(cli: Path) -> list[str]:
    return [str(cli), "core", "update-index"]


def install_core_cmd(cli: Path) -> list[str]:
    return [str(cli), "core", "install", ESP32_CORE]


def git_clone_cmd(url: str, dest: Path) -> list[str]:
    # --recursive: GP2040-CE 依赖 lib/tinyusb 等子模块
    return ["git", "clone", "--progress", "--recursive", url, str(dest)]


def core_install_cmd(cli: Path) -> list[str]:
    return [str(cli), "core", "install", ESP32_CORE]


__all__ = [
    "find_arduino_cli",
    "git_available",
    "core_installed",
    "cli_version",
    "config_init_cmd",
    "add_index_cmd",
    "update_index_cmd",
    "install_core_cmd",
    "git_clone_cmd",
    "core_install_cmd",
    "arduino_cli_download_url",
    "arduino_cli_exe_name",
]
