#!/usr/bin/env python3
"""组装「Win7 刷机包（免安装 · 不依赖 Python）」。

背景：Win7 上跑不了现在的编译工具链（Python 3.12/Qt6、arduino-cli 1.x、esp32 core 3.x
的 GCC 工具链都要求 Win10+），而便携 Python + PySide2 的方案在部分 Win7 机器上会被
安全软件/系统钩子干扰（进程启动阶段 `sys.executable` 变乱码 → 找不到 encodings）。

所以这个包只做刷写，而且**完全不依赖 Python**：

    esptool.exe（Espressif 官方 standalone，PyInstaller 单文件，只依赖 KERNEL32/ADVAPI32）
    + 预编译固件 + flash.bat 菜单 + diagnose.bat 自检

用法：
    python3 tools/make_win7_flashpack.py --out dist/GP-Combine-win7 \
        --firmware /tmp/lazy2/firmware
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ESPTOOL_VER = "4.8.1"          # 4.x：纯 Win7 兼容（5.x 要求更高版本 Python）
ESPTOOL_URL = ("https://github.com/espressif/esptool/releases/download/v%s/"
               "esptool-v%s-win64.zip" % (ESPTOOL_VER, ESPTOOL_VER))

# 分区偏移（与 firmware/partitions.csv 一致）
OFF_BOOTLOADER = "0x0"
OFF_PARTITIONS = "0x8000"
OFF_BOOT_APP0 = "0xe000"
OFF_APP = "0x10000"
OFF_LITTLEFS = "0x410000"


def fetch(url: str, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    print("下载", url)
    urllib.request.urlretrieve(url, dst)   # noqa: S310
    return dst


def write_gbk(path: Path, text: str) -> None:
    """Win7 中文 cmd 是 GBK，.bat 必须按 GBK 存，否则解析错乱。"""
    path.write_bytes(text.encode("gbk", errors="replace"))


def write_bats(out: Path) -> None:
    flash = f"""@echo off
setlocal enabledelayedexpansion
set "HERE=%~dp0"
title GP-Combine 刷机工具（Win7 免安装）

echo ============================================================
echo   GP-Combine 刷机工具    （不用装 Python / 不用装 Arduino）
echo ============================================================
echo.
echo 当前检测到的串口：
powershell -NoProfile -Command "[System.IO.Ports.SerialPort]::GetPortNames()" 2>nul
if errorlevel 1 echo   (检测失败，请到 设备管理器 -^> 端口 里看)
echo.
echo   提示：ESP32-S3 是免驱的；如果是 CP210x/CH340 板子要先装驱动。
echo         看不到端口就换一根"能传数据"的 USB 线，或按住 BOOTSEL 再插。
echo.
set "PORT="
set /p PORT=请输入串口号（例如 COM3，直接回车退出）: 
if "%PORT%"=="" exit /b

echo.
echo 选择要刷的固件：
echo    1 = 170x320 竖屏大屏
echo    2 = 240x135 小屏
echo    9 = 先整片擦除（清空所有设置和卡内文件，再刷 170x320）
set "RES="
set /p RES=请输入 1 / 2 / 9: 

if "%RES%"=="2"  (set "FW=%HERE%firmware\\esp32_240_135" & goto :go)
if "%RES%"=="9"  (set "FW=%HERE%firmware\\esp32_170_320" & set "ERASE=1" & goto :go)
set "FW=%HERE%firmware\\esp32_170_320"

:go
if not exist "%FW%\\app.bin" (
  echo.
  echo [错误] 找不到固件：%FW%\\app.bin
  echo        请确认压缩包解压完整。
  pause & exit /b 1
)

echo.
echo ============================================================
echo   串口: %PORT%
echo   固件: %FW%
echo   即将写入 bootloader + 分区表 + 应用（不会清卡内文件）
echo ============================================================
pause

if defined ERASE (
  echo.
  echo [1/2] 整片擦除...
  "%HERE%esptool.exe" --chip esp32s3 -p %PORT% --baud 921600 erase-flash
  if errorlevel 1 goto :fail
)

echo.
echo 写入固件...
"%HERE%esptool.exe" --chip esp32s3 -p %PORT% --baud 921600 write-flash ^
  {OFF_BOOTLOADER} "%FW%\\bootloader.bin" ^
  {OFF_PARTITIONS} "%FW%\\partitions.bin" ^
  {OFF_BOOT_APP0} "%FW%\\boot_app0.bin" ^
  {OFF_APP} "%FW%\\app.bin"
if errorlevel 1 goto :fail

if exist "%FW%\\littlefs.bin" (
  echo.
  echo 写入卡内文件（壁纸 / ROM）...
  "%HERE%esptool.exe" --chip esp32s3 -p %PORT% --baud 921600 write-flash {OFF_LITTLEFS} "%FW%\\littlefs.bin"
  if errorlevel 1 goto :fail
)

echo.
echo ============================================================
echo   ✔ 刷写完成！板子会自动重启。
echo ============================================================
pause
exit /b 0

:fail
echo.
echo ============================================================
echo   ✘ 刷写失败，检查：
echo     1. 串口是不是选错了（设备管理器里看）
echo     2. 驱动装了没（CP210x/CH340 需要；ESP32-S3 免驱）
echo     3. 换根 USB 线
echo     4. 先按住 BOOTSEL 再插 USB，然后重跑本脚本
echo ============================================================
pause
exit /b 1
"""
    diag = f"""@echo off
setlocal
set "HERE=%~dp0"
echo === GP-Combine 刷机包自检（把整个窗口内容发给作者）===
echo.
echo 当前路径: %HERE%
if exist "%HERE%esptool.exe" (echo [OK] esptool.exe) else (echo [缺] esptool.exe)
if exist "%HERE%firmware\\esp32_170_320\\app.bin" (echo [OK] 170x320 固件) else (echo [缺] 170x320 固件)
if exist "%HERE%firmware\\esp32_240_135\\app.bin" (echo [OK] 240x135 固件) else (echo [缺] 240x135 固件)
echo.
echo --- esptool 版本 ---
"%HERE%esptool.exe" version
echo.
echo --- 检测到的串口 ---
powershell -NoProfile -Command "[System.IO.Ports.SerialPort]::GetPortNames()"
echo.
echo --- Windows 版本 ---
ver
echo.
pause
"""
    write_gbk(out / "flash.bat", flash)
    write_gbk(out / "diagnose.bat", diag)
    write_gbk(out / "诊断.bat", diag)


def write_readme(out: Path) -> None:
    text = f"""GP-Combine 刷机工具（Win7 免安装）
=====================================

★ 用法：双击 flash.bat
    1. 先把板子插到 USB（ESP32-S3 免驱；CP210x/CH340 板子要先装驱动）
    2. 脚本会列出检测到的串口，输入串口号（例如 COM3）
    3. 选固件：1 = 170x320 竖屏大屏，2 = 240x135 小屏
    4. 确认后自动刷写，跑完板子自动重启

★ 这个包不含编译功能
    Win7 跑不了现在的编译工具链（Python 3.12/Qt6、arduino-cli 1.x、esp32 core 3.x
    的 GCC 工具链都要求 Win10+）。要改背景/布局/小游戏，请在 Win10/11 的完整懒人包
    里编译好后，把 firmware 里的 .bin 拷过来刷；或者直接在 Win10/11 上刷。

★ 出问题怎么办
    先双击 diagnose.bat（或 诊断.bat），把窗口内容发给作者：
    它会打印 esptool 版本、串口列表、Windows 版本。

★ 常用排查
    - 看不到串口：换一根能传数据的 USB 线；装 CP210x/CH340 驱动
    - 一直连接失败：按住 BOOTSEL 键再插 USB，然后重跑 flash.bat
    - 想清空所有设置：选 9（整片擦除后再刷）

esptool 版本: {ESPTOOL_VER}（Espressif 官方 standalone，仅依赖 KERNEL32/ADVAPI32，Win7 可跑）
"""
    write_gbk(out / "README-Win7.txt", text)


def main() -> int:
    ap = argparse.ArgumentParser(description="组装 Win7 刷机包（免 Python）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--firmware", required=True, help="含 esp32_240_135 / esp32_170_320 的目录")
    ap.add_argument("--cache", default="/tmp/gpwin7cache")
    ap.add_argument("--esptool-version", default=ESPTOOL_VER)
    args = ap.parse_args()

    out = Path(args.out).resolve()
    cache = Path(args.cache)
    fw_src = Path(args.firmware).expanduser().resolve()
    if not (fw_src / "esp32_170_320" / "app.bin").is_file():
        raise SystemExit("--firmware 里没有 esp32_170_320/app.bin：%s" % fw_src)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    # 1) esptool.exe（standalone）
    zip_path = cache / ("esptool-v%s-win64.zip" % args.esptool_version)
    if not zip_path.is_file():
        fetch(ESPTOOL_URL.replace(ESPTOOL_VER, args.esptool_version), zip_path)
    tmp = cache / "esptool-x"
    shutil.rmtree(tmp, ignore_errors=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(tmp)
    exe = next(tmp.rglob("esptool.exe"))
    shutil.copy2(exe, out / "esptool.exe")
    for extra in ("LICENSE", "README.md"):
        f = exe.parent / extra
        if f.is_file():
            shutil.copy2(f, out / ("esptool-" + extra))
    print("✔ esptool.exe", args.esptool_version, "→", out / "esptool.exe")

    # 2) 预编译固件
    shutil.copytree(fw_src, out / "firmware", dirs_exist_ok=True)
    for res in ("esp32_170_320", "esp32_240_135"):
        p = out / "firmware" / res
        print("✔ 固件 %s：%s" % (res, ", ".join(sorted(f.name for f in p.glob("*.bin"))) or "无"))

    # 3) 脚本 + 说明
    write_bats(out)
    write_readme(out)
    (out / "bundle.json").write_text(json.dumps({
        "name": "GP-Combine 刷机工具（Win7 免安装）",
        "esptool": args.esptool_version,
        "needs_python": False,
        "offsets": {"bootloader": OFF_BOOTLOADER, "partitions": OFF_PARTITIONS,
                    "boot_app0": OFF_BOOT_APP0, "app": OFF_APP, "littlefs": OFF_LITTLEFS},
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    total = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print("\n=== Win7 刷机包（免 Python）完成 ===")
    print("路径:", out)
    print("大小: %.1f MB" % (total / 1048576.0))
    print("入口:", out / "flash.bat")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
