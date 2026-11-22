"""工具链检测与命令构造：arduino-cli、ESP32 核心、git。"""
from __future__ import annotations

import shutil
import subprocess
import os
import urllib.request
from pathlib import Path

from .app_config import (
    ESP32_CORE,
    ESP32_INDEX_URL,
    ESP32_INDEX_URL_MIRRORS,
    arduino_cli_exe_name,
    default_cli_path,
    is_windows,
)


def find_arduino_cli() -> Path | None:
    """优先用户默认工具目录，其次系统 PATH。"""
    default = default_cli_path()
    if default.is_file():
        return default
    found = shutil.which("arduino-cli")
    if found:
        return Path(found)
    # Windows：winget 装完可能不在当前进程 PATH，扫描 winget 安装目录
    if is_windows():
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Microsoft" / "WinGet" / "Packages"
        if base.is_dir():
            hits = sorted(base.rglob("arduino-cli.exe"))
            if hits:
                return hits[0]
    return None


def winget_install_cmd() -> list[str]:
    return [
        "winget", "install", "--id", "ArduinoSA.CLI",
        "--accept-package-agreements", "--accept-source-agreements",
    ]


def linux_install_hint() -> str:
    return (
        "本机未检测到 arduino-cli。\n\n"
        "请打开终端自行安装：\n"
        "  Arch/Manjaro:  sudo pacman -S arduino-cli\n"
        "  Debian/Ubuntu: sudo apt install arduino-cli\n\n"
        "安装完成后点「刷新检测」继续。"
    )


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


def url_reachable(url: str, timeout: float = 4.0) -> bool:
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return 200 <= r.status < 400
    except Exception:
        return False


def pick_esp32_index_url(timeout: float = 2.5) -> str:
    """选一个能连通的下载源：环境变量 > jsDelivr > 官方。

    注意：这个探测是同步的（会挡 UI），所以超时压到 2.5s；
    两个源都不通就直接用官方，交给 arduino-cli 自己报错。
    """
    env = os.environ.get("GPFUSION_ESP32_INDEX")
    if env:
        return env
    for url in ESP32_INDEX_URL_MIRRORS:
        if url_reachable(url, timeout):
            return url
    return ESP32_INDEX_URL


def add_index_cmd(cli: Path, url: str | None = None) -> list[str]:
    return [str(cli), "config", "add", "board_manager.additional_urls", url or ESP32_INDEX_URL]


def update_index_cmd(cli: Path) -> list[str]:
    return [str(cli), "core", "update-index"]


def install_core_cmd(cli: Path) -> list[str]:
    return [str(cli), "core", "install", ESP32_CORE]


def git_clone_cmd(url: str, dest: Path) -> list[str]:
    # --recursive: GP2040-CE 依赖 lib/tinyusb 等子模块
    return ["git", "clone", "--progress", "--recursive", url, str(dest)]


def core_install_cmd(cli: Path) -> list[str]:
    return [str(cli), "core", "install", ESP32_CORE]


def core_uninstall_cmd(cli: Path) -> list[str]:
    return [str(cli), "core", "uninstall", ESP32_CORE]


def core_staging_dirs() -> list[Path]:
    """arduino-cli 下载缓存目录（下载中断残留就在这里）。"""
    dirs: list[Path] = []
    if is_windows():
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Arduino15"
    else:
        base = Path.home() / ".arduino15"
    for sub in ("staging", "staging/packages"):
        dirs.append(base / sub)
    return dirs


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
    "arduino_cli_exe_name",
]
