"""工具链检测与命令构造：arduino-cli、ESP32 核心、git。"""
from __future__ import annotations

import json
import shutil
import subprocess
import os
import urllib.request
from pathlib import Path

from .app_config import (
    ESP32_CORE,
    ESP32_INDEX_URL,
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


def add_index_cmd(cli: Path) -> list[str]:
    return [str(cli), "config", "add", "board_manager.additional_urls", ESP32_INDEX_URL]


def update_index_cmd(cli: Path) -> list[str]:
    return [str(cli), "core", "update-index"]


def install_core_cmd(cli: Path) -> list[str]:
    return [str(cli), "core", "install", ESP32_CORE]


def git_clone_cmd(url: str, dest: Path) -> list[str]:
    # --recursive: GP2040-CE 依赖 lib/tinyusb 等子模块
    return ["git", "clone", "--progress", "--recursive", url, str(dest)]


def arduino_data_dir() -> Path:
    if is_windows():
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Arduino15"
    return Path.home() / ".arduino15"


def esp32_archive_info() -> tuple[str, str, int] | None:
    """从 arduino-cli 缓存的索引里取最新 ESP32 平台的 (下载地址, 文件名, 字节数)。

    用来做断点续传：arduino-cli 自己不支持续传，断了就从 0 开始。
    """
    idx = arduino_data_dir() / "package_esp32_index.json"
    try:
        data = json.loads(idx.read_text(encoding="utf-8"))
    except Exception:
        return None
    for pkg in data.get("packages", []):
        if pkg.get("name") != "esp32":
            continue
        plats = [p for p in pkg.get("platforms", []) if p.get("url")]
        if not plats:
            return None
        plats.sort(key=lambda p: [int(x) if x.isdigit() else 0
                                  for x in str(p.get("version", "0")).replace("-", ".").split(".")])
        p = plats[-1]
        url = p["url"]
        name = p.get("archiveFileName") or url.rsplit("/", 1)[-1]
        return url, name, int(p.get("size") or 0)
    return None


def core_download_cmd(cli: Path) -> list[str]:
    return [str(cli), "core", "download", ESP32_CORE]


def resume_download_cmd(url: str, dest: Path) -> list[str]:
    """curl 断点续传：-C - 从已有文件的末尾继续，网络抖动能接上。"""
    return ["curl", "-L", "-C", "-", "--retry", "5", "--retry-delay", "3",
            "-o", str(dest), url]


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
