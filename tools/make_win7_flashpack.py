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


def write_launchers(out: Path) -> None:
    """写启动器。

    要点：
    * .bat 用 GBK(cp936) 编码，中文 Windows 的 cmd 才显示正常；
    * 路径含中文时 embedded Python 会 getpath 崩（sys.executable 变乱码 ->
      ModuleNotFoundError: No module named 'encodings'），所以先用 PowerShell
      检测非 ASCII 字符，命中就自动复制到 %LOCALAPPDATA%\\GPCombine 再跑。
    """
    start = (
        "@echo off\r\n"
        "setlocal\r\n"
        'set "HERE=%~dp0"\r\n'
        "for /f \"delims=\" %%p in (\"%HERE%\") do set \"P=%%~p\"\r\n"
        "powershell -NoProfile -ExecutionPolicy Bypass -Command \"if ('%P%' -match '[^\\x20-\\x7e]') { exit 1 } else { exit 0 }\"\r\n"
        "if errorlevel 1 goto relocate\r\n"
        'set "GPCOMBINE_BUNDLE=%HERE%"\r\n'
        'set "PATH=%HERE%python;%PATH%"\r\n'
        "echo 正在启动 GP-Combine 懒人版（Win7 刷机包）...\r\n"
        '"%HERE%python\\python.exe" "%HERE%app\\pcapp_dumbversion\\main.py" --bundle "%HERE%" %*\r\n'
        "if errorlevel 1 pause\r\n"
        "exit /b\r\n"
        ":relocate\r\n"
        "echo.\r\n"
        "echo [提示] 当前路径含中文或特殊字符：\r\n"
        "echo        %HERE%\r\n"
        "echo        内置 Python 在这种路径下无法启动，正在自动复制到：\r\n"
        "echo        %LOCALAPPDATA%\\GPCombine\r\n"
        "echo        复制完会自动打开，请稍等（约 350MB）...\r\n"
        'xcopy /E /I /Q /Y "%HERE:~0,-1%" "%LOCALAPPDATA%\\GPCombine\\" >nul\r\n'
        'start "" "%LOCALAPPDATA%\\GPCombine\\Start-GP-Combine.bat"\r\n'
        "exit /b\r\n"
    )
    diag = (
        "@echo off\r\n"
        'set "HERE=%~dp0"\r\n'
        'set "GPCOMBINE_BUNDLE=%HERE%"\r\n'
        'set "PATH=%HERE%python;%PATH%"\r\n'
        "echo === GP-Combine 环境自检（把整个窗口内容发给作者）===\r\n"
        "echo.\r\n"
        "echo 当前路径: %HERE%\r\n"
        "echo.\r\n"
        "echo --- 关键文件检查（应该都有）---\r\n"
        'if exist "%HERE%python\\python.exe" (echo [OK] python.exe) else (echo [缺] python.exe)\r\n'
        'if exist "%HERE%python\\python38.zip" (echo [OK] python38.zip) else (echo [缺] python38.zip)\r\n'
        'if exist "%HERE%python\\python38._pth" (echo [OK] python38._pth) else (echo [缺] python38._pth)\r\n'
        'if exist "%HERE%python\\Lib\\site-packages\\PySide2\\__init__.py" (echo [OK] PySide2) else (echo [缺] PySide2)\r\n'
        'if exist "%HERE%python\\Lib\\site-packages\\esptool\\__main__.py" (echo [OK] esptool) else (echo [缺] esptool)\r\n'
        "echo.\r\n"
        "echo --- 解释器能不能起来（应打印 Python 3.8.x）---\r\n"
        '"%HERE%python\\python.exe" -V\r\n'
        "echo.\r\n"
        "echo --- 助手自检 ---\r\n"
        '"%HERE%python\\python.exe" "%HERE%app\\pcapp_dumbversion\\main.py" --bundle "%HERE%" --selftest\r\n'
        "echo.\r\n"
        "pause\r\n"
    )
    for name, text in (("Start-GP-Combine.bat", start),
                       ("diagnose.bat", diag),
                       ("诊断-显示详细报错.bat", diag)):
        (out / name).write_bytes(text.encode("gbk", errors="replace"))
    print("✔ 启动器（GBK）")


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
    write_launchers(out)
    (out / "README-Win7.txt").write_text(
        "GP-Combine 懒人版 · Win7 刷机包\r\n"
        "================================\r\n\r\n"
        "★★★ 重要：必须放到纯英文路径！★★★\r\n"
        "   例如 D:\\GP-Combine   （不要放在 桌面/新建文件夹/中文目录 里）\r\n"
        "   内置的 Python 3.8 在中文路径下会启动失败；\r\n"
        "   如果放错了，双击 Start-GP-Combine.bat 会自动把它复制到\r\n"
        "   %LOCALAPPDATA%\\GPCombine 再启动（会慢一点，但能跑）。\r\n\r\n"
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
