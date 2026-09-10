"""把壁纸文件写入设备 LittleFS：mklittlefs 打包 + esptool 按分区偏移烧写。

适用于正式版两块 N16R8 板（240x135 与 170x320 用同一分区表：
LittleFS 位于 0x310000，大小 12.94MB）。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

FS_OFFSET = "0x310000"
FS_SIZE = 0xCF0000            # 12.94 MB
FS_BLOCK = 4096
FS_PAGE = 256


def _arduino15() -> Path:
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(base) / "Arduino15"
    return Path.home() / ".arduino15"


def _find_tool(name: str, exe: str) -> Path | None:
    root = _arduino15() / "packages" / "esp32" / "tools" / name
    if not root.is_dir():
        return None
    hits = sorted(root.glob("*/%s" % exe))
    return hits[-1] if hits else None


def find_mklittlefs() -> Path | None:
    exe = "mklittlefs.exe" if sys.platform.startswith("win") else "mklittlefs"
    found = _find_tool("mklittlefs", exe)
    if found:
        return found
    which = shutil.which("mklittlefs")
    return Path(which) if which else None


def find_esptool() -> list[str] | None:
    """返回可直接执行的 esptool 命令前缀。"""
    py = _find_tool("esptool_py", "esptool.py")
    if py:
        return [sys.executable, str(py)]
    exe = "esptool.exe" if sys.platform.startswith("win") else "esptool"
    found = _find_tool("esptool_py", exe)
    if found:
        return [str(found)]
    which = shutil.which("esptool")
    if which:
        return [which]
    try:
        import esptool  # noqa: F401
        return [sys.executable, "-m", "esptool"]
    except Exception:  # noqa: BLE001
        return None


def build_fs_image(data_dir: Path, out_img: Path) -> tuple[bool, str]:
    """把 data_dir（内含 wp/1.gfr）打包成 LittleFS 镜像。"""
    tool = find_mklittlefs()
    if tool is None:
        return False, "找不到 mklittlefs（需先安装 ESP32 核心）"
    cmd = [str(tool), "-c", str(data_dir), "-b", str(FS_BLOCK),
           "-p", str(FS_PAGE), "-s", hex(FS_SIZE), str(out_img)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except Exception as exc:  # noqa: BLE001
        return False, "mklittlefs 执行失败：%s" % exc
    if r.returncode != 0:
        return False, "mklittlefs 失败：%s" % (r.stderr or r.stdout or "").strip()
    if not out_img.is_file():
        return False, "mklittlefs 未生成镜像"
    return True, "已生成 %s（%.1f MB）" % (out_img.name, out_img.stat().st_size / 1048576)


def flash_fs_cmd(port: str, img: Path) -> list[str] | None:
    esptool = find_esptool()
    if esptool is None:
        return None
    return esptool + ["--chip", "esp32s3", "-p", port, "--baud", "921600",
                      "write-flash", FS_OFFSET, str(img)]
