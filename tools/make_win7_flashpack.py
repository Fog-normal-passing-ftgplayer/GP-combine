#!/usr/bin/env python3
"""组装「Win7 刷机包」：不装 Python / Arduino，双击就能刷预先编译好的固件。

Win7 上没法跑现在的编译环境（Python 3.12/Qt6 要 Win10+、arduino-cli 1.x 是
Go 1.21+ 构建也要 Win10+、esp32 core 3.x 的 GCC 14 工具链同样如此），
所以这个包只做「刷写」：

    python-3.8 embed + PySide2(Qt5) + esptool 4.8（纯 Python）
    + 预编译固件（app/bootloader/partitions/boot_app0，可选 littlefs.bin）
    + 懒人版助手（同一份代码，编译相关按钮自动置灰）

用法：
    python3 tools/make_win7_flashpack.py --out dist/GP-Combine-win7 \
        --firmware /tmp/lazy2/firmware           # 或者 CI bundle 里的 firmware/
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

PY_VER = "3.8.10"
PY_URL = "https://www.python.org/ftp/python/%s/python-%s-embed-amd64.zip" % (PY_VER, PY_VER)
ESPTOOL_VER = "4.8.1"
WHEELS = ["PySide2==5.15.2.1", "pyserial", "Pillow==10.4.0", "reedsolo", "ecdsa", "bitstring"]


def sh(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    print("$", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run([str(c) for c in cmd], text=True, **kw)


def fetch(url: str, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    print("下载", url)
    urllib.request.urlretrieve(url, dst)   # noqa: S310
    return dst


def unzip(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src) as z:
        z.extractall(dst)


def install_wheels(wheels_dir: Path, site_packages: Path) -> None:
    site_packages.mkdir(parents=True, exist_ok=True)
    for whl in sorted(wheels_dir.glob("*.whl")):
        print("  安装", whl.name)
        with zipfile.ZipFile(whl) as z:
            z.extractall(site_packages)


def main() -> int:
    ap = argparse.ArgumentParser(description="组装 Win7 刷机包")
    ap.add_argument("--out", required=True)
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument("--firmware", default="", help="含 esp32_240_135/esp32_170_320 的目录")
    ap.add_argument("--cache", default=str(Path("/tmp/gpwin7cache")), help="下载缓存目录")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    out = Path(args.out).resolve()
    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)
    if out.exists():
        shutil.rmtree(out)
    (out / "python").mkdir(parents=True)
    (out / "app").mkdir(parents=True)
    (out / "src" / "GP-Combine").mkdir(parents=True)

    # 1) Python 3.8 embeddable（官方最后支持 Win7 的版本线）
    py_zip = cache / Path(PY_URL).name
    if not py_zip.is_file():
        fetch(PY_URL, py_zip)
    unzip(py_zip, out / "python")
    pth = out / "python" / "python38._pth"
    pth.write_text("python38.zip\n.\nLib\\site-packages\nimport site\n", encoding="utf-8")
    print("✔ python 3.8 embed →", out / "python")

    # 2) Win7 可用的轮子（PySide2=Qt5、Pillow、pyserial）
    wheels = cache / "wheels"
    if not wheels.is_dir() or not list(wheels.glob("*.whl")):
        wheels.mkdir(parents=True, exist_ok=True)
        sh([sys.executable, "-m", "pip", "download", "--no-deps", "--only-binary=:all:",
            "--platform", "win_amd64", "--python-version", "38", "--implementation", "cp",
            "--abi", "cp38", "-d", wheels, *WHEELS])
    install_wheels(wheels, out / "python" / "Lib" / "site-packages")

    # 3) esptool 4.8.1（纯 Python，Win7 可跑；5.x 需要更高 Python）
    import tarfile

    esp_tar = cache / ("esptool-%s.tar.gz" % ESPTOOL_VER)
    if not esp_tar.is_file():
        import json as _json

        with urllib.request.urlopen("https://pypi.org/pypi/esptool/%s/json" % ESPTOOL_VER) as r:  # noqa: S310
            meta = _json.load(r)
        url = next(u["url"] for u in meta["urls"] if u["filename"].endswith(".tar.gz"))
        fetch(url, esp_tar)
    tmp_ex = cache / "esptool-x"
    shutil.rmtree(tmp_ex, ignore_errors=True)
    with tarfile.open(esp_tar) as t:
        t.extractall(tmp_ex)
    inner = next(tmp_ex.glob("esptool-*"))
    shutil.copytree(inner / "esptool", out / "python" / "Lib" / "site-packages" / "esptool",
                    dirs_exist_ok=True)
    for extra in ("LICENSE", "README.md"):
        f = inner / extra
        if f.is_file():
            shutil.copy2(f, out / "python" / "Lib" / "site-packages" / ("esptool-" + extra))
    print("✔ esptool", ESPTOOL_VER)

    # 4) 懒人版助手 + 它用到的 pc_app 模块
    app_dir = out / "app" / "pcapp_dumbversion"
    app_dir.mkdir(parents=True, exist_ok=True)
    for name in ("main.py", "README.md"):
        f = repo / "pcapp_dumbversion" / name
        if f.is_file():
            shutil.copy2(f, app_dir / name)
    shutil.copytree(repo / "pcapp_dumbversion" / "dumb",
                    app_dir / "dumb", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(repo / "pc_app" / "gpfusion_wizard",
                    out / "src" / "GP-Combine" / "pc_app" / "gpfusion_wizard",
                    ignore=shutil.ignore_patterns("__pycache__", "ui"), dirs_exist_ok=True)
    (out / "src" / "GP-Combine" / "pc_app" / "__init__.py").write_text("", encoding="utf-8")
    print("✔ 助手 + pc_app 模块")

    # 5) 预编译固件
    fw_src = Path(args.firmware).expanduser() if args.firmware else None
    if fw_src and fw_src.is_dir():
        shutil.copytree(fw_src, out / "firmware", dirs_exist_ok=True)
        print("✔ 预编译固件 →", out / "firmware")
    else:
        print("⚠ 没有提供 --firmware，包里不会有固件（刷不了）")

    # 6) 启动器 + 说明
    (out / "Start-GP-Combine.bat").write_text(
        "@echo off\r\n"
        "setlocal\r\n"
        'set "HERE=%~dp0"\r\n'
        'set "GPCOMBINE_BUNDLE=%HERE%"\r\n'
        'set "PATH=%HERE%python;%PATH%"\r\n'
        'echo 正在启动 GP-Combine 懒人版（Win7 刷机包）...\r\n'
        '"%HERE%python\\python.exe" "%HERE%app\\pcapp_dumbversion\\main.py" --bundle "%HERE%" %*\r\n'
        "if errorlevel 1 pause\r\n"
        "endlocal\r\n",
        encoding="utf-8",
    )
    (out / "诊断-显示详细报错.bat").write_text(
        "@echo off\r\n"
        'set "HERE=%~dp0"\r\n'
        'set "GPCOMBINE_BUNDLE=%HERE%"\r\n'
        '"%HERE%python\\python.exe" "%HERE%app\\pcapp_dumbversion\\main.py" --bundle "%HERE%" --selftest\r\n'
        "pause\r\n",
        encoding="utf-8",
    )
    (out / "README-Win7.txt").write_text(
        "GP-Combine 懒人版 · Win7 刷机包\r\n"
        "================================\r\n\r\n"
        "这个包只做「刷写」，不编译。\r\n"
        "Win7 上没法跑现在的编译工具链（Python 3.12/Qt6、arduino-cli 1.x、esp32 core 3.x\r\n"
        "的 GCC 工具链都要求 Win10+），所以编译请在 Win10/11 的完整懒人包里做。\r\n\r\n"
        "怎么用：\r\n"
        "1. 把整块板子插到电脑 USB（ESP32-S3 免驱；CP210x/CH340 的板子要先装驱动）\r\n"
        "2. 双击 Start-GP-Combine.bat\r\n"
        "3. 顶部「串口」下拉选到板子的端口（看不到就点刷新）\r\n"
        "4. 想要哪块屏就选分辨率，然后点「刷预编译固件」\r\n"
        "   - 想清空重来：先「整机重刷」→ 不行再用命令行 esptool erase-flash\r\n"
        "5. 动态壁纸/小游戏 ROM：需要别人用完整版助手写卡内文件，或者用完整包里的\r\n"
        "   「写入卡内文件」按钮（这个包也支持，只要 firmware 里带了 littlefs.bin）\r\n\r\n"
        "出问题时：\r\n"
        "- 双击「诊断-显示详细报错.bat」，把窗口里的内容发给作者\r\n"
        "- 板子不识别：换根 USB 线（要能传数据的），或者按住 BOOTSEL 再插\r\n",
        encoding="utf-8",
    )

    manifest = {
        "name": "GP-Combine 懒人包（Win7 刷机包）",
        "python": PY_VER,
        "gui": "PySide2 (Qt5)",
        "esptool": ESPTOOL_VER,
        "firmware": bool(fw_src and fw_src.is_dir()),
    }
    (out / "bundle.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    total = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print("\n=== Win7 刷机包完成 ===")
    print("路径:", out)
    print("大小: %.1f MB" % (total / 1048576.0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
