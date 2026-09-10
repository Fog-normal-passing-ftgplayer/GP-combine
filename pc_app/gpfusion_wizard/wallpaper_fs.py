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

FS_OFFSET = "0x410000"
FS_SIZE = 0xBF0000            # 11.94 MB
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


# ---------------- 整机重刷（bootloader + 分区表 + app [+ 卡内文件]） ----------------

APP_OFFSET = "0x10000"
BOOTLOADER_OFFSET = "0x0"
PARTITIONS_OFFSET = "0x8000"
BOOT_APP0_OFFSET = "0xe000"


def erase_flash_cmd(port: str) -> list[str] | None:
    esptool = find_esptool()
    if esptool is None:
        return None
    return esptool + ["--chip", "esp32s3", "-p", port, "erase-flash"]


def full_flash_cmd(port: str, bootloader: Path, partitions: Path,
                   boot_app0: Path, app: Path,
                   fs_img: Path | None = None) -> list[str] | None:
    """整机写入命令（分区表变更后必须走这条）。"""
    esptool = find_esptool()
    if esptool is None:
        return None
    cmd = esptool + ["--chip", "esp32s3", "-p", port, "--baud", "921600",
                     "write-flash",
                     BOOTLOADER_OFFSET, str(bootloader),
                     PARTITIONS_OFFSET, str(partitions),
                     BOOT_APP0_OFFSET, str(boot_app0),
                     APP_OFFSET, str(app)]
    if fs_img is not None:
        cmd += [FS_OFFSET, str(fs_img)]
    return cmd


def stage_fs_image(files: list[tuple[Path, str]], out_img: Path) -> tuple[bool, str]:
    """把 (源文件, 卡内路径) 列表打包成 LittleFS 镜像（临时目录暂存）。"""
    import tempfile

    with tempfile.TemporaryDirectory(prefix="gpfusion_fs_") as tmp:
        root = Path(tmp)
        for src, inner in files:
            dst = root / inner.lstrip("/")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return build_fs_image(root, out_img)
