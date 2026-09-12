#!/usr/bin/env python3
"""打包「GP-Combine 懒人包」：arduino-cli + esp32 core + 源码 + 懒人版助手。

典型用法（开发机上跑一次，产出给用户直接解压用）：

    # 从零装 core（需要网络 / 梯子）
    python3 tools/make_bundle.py --out dist/GP-Combine-lazy

    # 复用本机 ~/.arduino15 已装好的 core（推荐，快很多）
    python3 tools/make_bundle.py --out dist/GP-Combine-lazy \
        --from-data ~/.arduino15 --cli $(which arduino-cli)

    # 开发自测：core 用软链接，不占空间
    python3 tools/make_bundle.py --out /tmp/lazy --link-core ~/.arduino15

    # 顺带把两版固件编译好放进 firmware/（用户可「刷预编译固件」）
    python3 tools/make_bundle.py --out dist/GP-Combine-lazy --prebuilt --zip
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

CORE_SPEC = "esp32:esp32"
CORE_VERSION = "3.3.11"
FQBN = "esp32:esp32:esp32s3:PSRAM=opi,FlashSize=16M,PartitionScheme=custom"


def utf8_stdio() -> None:
    """Windows 控制台默认 cp1252，打印 ✔ / → 会 UnicodeEncodeError。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

# 只编 ESP32-S3：这些工具/目录打包时删掉，能省一半体积
# 只编 ESP32-S3：tools/ 下只保留这些，其余（其它目标的预编译库、gdb、openocd、
# riscv 工具链）全部删掉，能省一半体积
KEEP_TOOLS = ("esp-x32", "esp32s3-libs", "esptool_py", "mklittlefs", "mkspiffs")
PRUNE_DATA_DIRS = ("staging", "tmp", "cache/tmp")
# 数据目录根下的元数据：没有它们 arduino-cli 首次编译会尝试联网下载
INDEX_FILES = (
    "package_index.json",
    "package_index.json.sig",
    "library_index.json",
    "inventory.yaml",
    "arduino-cli.yaml",
)
SRC_EXCLUDES = (
    ".git", "node_modules", "__pycache__", ".venv", "pc_app.zip",
    "ESP-DOOM", "esp32-doom", "InfoNES-master", "build", "build_fusion",
    "build_receiver", "build_receiver_zero", "build-reverse", "dist",
)


def sh(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    print("$", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run([str(c) for c in cmd], text=True, **kw)


def cli_name() -> str:
    return "arduino-cli.exe" if os.name == "nt" else "arduino-cli"


def find_cli(explicit: str | None) -> Path | None:
    if explicit:
        p = Path(explicit).expanduser()
        return p if p.is_file() else None
    found = shutil.which("arduino-cli")
    if found:
        return Path(found)
    for cand in (
        Path.home() / ".gpfusion" / "tools" / "arduino-cli" / cli_name(),
        Path(os.environ.get("LOCALAPPDATA", Path.home())) / "GPFusion" / "tools" / "arduino-cli" / cli_name(),
    ):
        if cand.is_file():
            return cand
    return None


def find_arduino_data(explicit: str | None) -> Path | None:
    if explicit:
        p = Path(explicit).expanduser()
        return p if p.is_dir() else None
    env = os.environ.get("ARDUINO_DIRECTORIES_DATA")
    if env and Path(env).is_dir():
        return Path(env)
    for cand in (
        Path.home() / ".arduino15",
        Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Arduino15",
    ):
        if cand.is_dir():
            return cand
    return None


def copytree(src: Path, dst: Path, skip_names: tuple[str, ...] = ()) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.name in skip_names:
            continue
        target = dst / item.name
        if item.is_dir():
            copytree(item, target, skip_names)
        else:
            shutil.copy2(item, target)


def copy_tool(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    if os.name != "nt":
        dst.chmod(0o755)


SKETCH_SNAPSHOT = (
    "esp32",
    "esp32_170x320",
    "pc_app",
    "background",
    "icons",
    "LICENSE",
    "README.md",
    "GP-Combine-logo.png",
)


def copy_snapshot(repo: Path, dst: Path, mode: str) -> None:
    """复制源码快照。

    mode=sketch（默认，ESP32 懒人包）：只带两版 ESP32 sketch + pc_app 的 Python 包；
    mode=full：整仓库（去掉 .git / 构建目录 / 大依赖）。
    """
    dst.mkdir(parents=True, exist_ok=True)
    if mode == "full":
        copytree(repo, dst, skip_names=SRC_EXCLUDES)
    else:
        for name in SKETCH_SNAPSHOT:
            src = repo / name
            if not src.exists():
                continue
            target = dst / name
            if src.is_dir():
                copytree(src, target, skip_names=("build", "__pycache__", "dist", ".venv"))
            else:
                shutil.copy2(src, target)
    # 卡内文件目录（动态壁纸 / ROM 会写到这里）
    for rel in ("data/wp", "data/nes"):
        (dst / rel).mkdir(parents=True, exist_ok=True)


def prune_arduino_data(data: Path) -> None:
    # 只留 esp32 这个包（arduino:mbed_rp2040 之类用不到）
    packages = data / "packages"
    if packages.is_dir():
        for pkg in list(packages.iterdir()):
            if pkg.name in ("esp32", "builtin"):
                continue
            print("  裁剪包", pkg.name)
            shutil.rmtree(pkg, ignore_errors=True)
    tools = data / "packages" / "esp32" / "tools"
    if tools.is_dir():
        for item in list(tools.iterdir()):
            if item.name in KEEP_TOOLS:
                continue
            print("  裁剪工具", item.name)
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                item.unlink(missing_ok=True)
    for rel in PRUNE_DATA_DIRS:
        target = data / rel
        if target.exists():
            print("  清理", target)
            shutil.rmtree(target, ignore_errors=True)


def copy_arduino_data(from_data: Path, data_dst: Path) -> None:
    """按需复制 core：只带 esp32 包，tools/ 只带 S3 用得到的那几个。

    直接复制整个 ~/.arduino15 是 5GB+（各芯片工具链），这样只拷约 1.5GB。
    """
    src_pkg = from_data / "packages" / "esp32"
    dst_pkg = data_dst / "packages" / "esp32"
    if not src_pkg.is_dir():
        raise SystemExit("%s 下没有 packages/esp32" % from_data)
    hw = src_pkg / "hardware"
    if hw.is_dir():
        for item in hw.iterdir():
            print("  复制 hardware/%s" % item.name)
            copytree(item, dst_pkg / "hardware" / item.name, skip_names=("build",))
    tools = src_pkg / "tools"
    if tools.is_dir():
        for item in tools.iterdir():
            if item.name not in KEEP_TOOLS:
                continue
            print("  复制 tools/%s" % item.name)
            copytree(item, dst_pkg / "tools" / item.name, skip_names=("tmp",))
    # builtin 只有几 MB（串口 / MDNS 发现工具），带上更保险
    builtin = from_data / "packages" / "builtin"
    if builtin.is_dir():
        print("  复制 packages/builtin")
        copytree(builtin, data_dst / "packages" / "builtin", skip_names=("tmp",))
    for extra in INDEX_FILES:
        f = from_data / extra
        if f.is_file():
            print("  复制 %s" % extra)
            shutil.copy2(f, data_dst / extra)


def bundle_cli_env(root: Path) -> dict:
    """给 arduino-cli 子进程用的环境：强制走包内 core，且不要联网检查更新。"""
    data = root / "arduino-data"
    user = root / "arduino-user"
    user.mkdir(parents=True, exist_ok=True)
    return dict(
        os.environ,
        ARDUINO_DIRECTORIES_DATA=str(data),
        ARDUINO_DIRECTORIES_USER=str(user),
        ARDUINO_CONFIG_FILE=str(root / "arduino-cli.yaml"),
        ARDUINO_UPDATER_ENABLE_NOTIFICATION="false",
        PYTHONUTF8="1",
        PYTHONIOENCODING="utf-8",
        NO_PROXY="*",
    )


def count_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += (Path(root) / f).stat().st_size
            except OSError:
                pass
    return total


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return "%.1f %s" % (n, unit)
        n /= 1024.0
    return "%d B" % n


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_launchers(root: Path) -> None:
    (root / "start-linux.sh").write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"\n'
        'export GPCOMBINE_BUNDLE="$HERE"\n'
        'PY="$HERE/python/bin/python3"\n'
        '[ -x "$PY" ] || PY=python3\n'
        'exec "$PY" "$HERE/app/pcapp_dumbversion/main.py" --bundle "$HERE" "$@"\n',
        encoding="utf-8",
    )
    (root / "start-linux.sh").chmod(0o755)
    (root / "Start-GP-Combine.bat").write_text(
        "@echo off\r\n"
        "setlocal\r\n"
        'set "HERE=%~dp0"\r\n'
        'set "GPCOMBINE_BUNDLE=%HERE%"\r\n'
        'if exist "%HERE%python\\python.exe" (\r\n'
        '  "%HERE%python\\python.exe" "%HERE%app\\pcapp_dumbversion\\main.py" --bundle "%HERE%" %*\r\n'
        ") else (\r\n"
        '  python "%HERE%app\\pcapp_dumbversion\\main.py" --bundle "%HERE%" %*\r\n'
        ")\r\n"
        "endlocal\r\n",
        encoding="utf-8",
    )


def build_prebuilt(root: Path, cli: Path, source: Path, work: Path) -> None:
    """把两版固件编译好放进 firmware/（走「刷预编译固件」按钮）。"""
    env = bundle_cli_env(root)
    for res, sketch_name in (("240x135", "esp32"), ("170x320", "esp32_170x320")):
        sketch = source / sketch_name
        out = work / ("prebuilt_" + sketch_name)
        out.mkdir(parents=True, exist_ok=True)
        proc = sh([cli, "compile", "--fqbn", FQBN, "--build-path", out, sketch],
                  capture_output=True, env=env)
        if proc.returncode != 0:
            print(proc.stdout[-2000:] or proc.stderr[-2000:])
            raise SystemExit("编译 %s 失败" % res)
        dst = root / "firmware" / ("esp32_%s" % res.replace("x", "_"))
        dst.mkdir(parents=True, exist_ok=True)
        mapping = {
            sketch_name + ".ino.bin": "app.bin",
            sketch_name + ".ino.bootloader.bin": "bootloader.bin",
            sketch_name + ".ino.partitions.bin": "partitions.bin",
            "boot_app0.bin": "boot_app0.bin",
        }
        for src_name, dst_name in mapping.items():
            src = out / src_name
            if src.is_file():
                shutil.copy2(src, dst / dst_name)
        shutil.rmtree(out, ignore_errors=True)      # 构建中间产物不进包
        print("  预编译固件 →", dst)


def main() -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(description="打包 GP-Combine 懒人包")
    ap.add_argument("--out", required=True, help="输出目录（懒人包根）")
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument("--cli", default="", help="arduino-cli 路径（默认自动找）")
    ap.add_argument("--core-version", default=CORE_VERSION)
    ap.add_argument("--from-data", default="", help="复用已装好的 Arduino15 目录（快）")
    ap.add_argument("--link-core", default="", help="开发用：arduino-data 软链接到该目录")
    ap.add_argument("--prebuilt", action="store_true", help="顺带编译两版固件放到 firmware/")
    ap.add_argument("--with-pico", action="store_true", help="附带 pico-sdk（完整版）")
    ap.add_argument("--src-mode", choices=("sketch", "full"), default="sketch",
                    help="源码快照范围：sketch=只要两版 ESP32 与 pc_app（默认，体积小）")
    ap.add_argument("--pico-sdk", default=str(Path.home() / "pico" / "pico-sdk"))
    ap.add_argument("--zip", action="store_true", help="打包成 zip")
    ap.add_argument("--keep-core", action="store_true", help="不裁剪 core 里的其它目标工具")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    root = Path(args.out).resolve()
    if root.exists():
        print("清空已存在的输出目录：", root)
        shutil.rmtree(root)
    for sub in ("app", "tools", "arduino-user", "firmware", "work", "src"):
        (root / sub).mkdir(parents=True, exist_ok=True)

    # 1) arduino-cli
    cli_src = find_cli(args.cli or None)
    if cli_src is None:
        raise SystemExit("找不到 arduino-cli，请用 --cli 指定")
    cli_dst = root / "tools" / "arduino-cli" / cli_name()
    copy_tool(cli_src, cli_dst)
    print("✔ arduino-cli:", cli_src, "→", cli_dst)

    # 2) arduino-data（esp32 core）
    data_dst = root / "arduino-data"
    if args.link_core:
        src = Path(args.link_core).expanduser().resolve()
        if not src.is_dir():
            raise SystemExit("--link-core 目录不存在：%s" % src)
        os.symlink(src, data_dst, target_is_directory=True)
        print("✔ arduino-data 软链接 →", src, "（开发模式）")
    else:
        from_data = find_arduino_data(args.from_data or None)
        if from_data is not None:
            print("复制 Arduino 数据目录（只带 esp32 包）：", from_data)
            data_dst.mkdir(parents=True, exist_ok=True)
            copy_arduino_data(from_data, data_dst)
        else:
            data_dst.mkdir(parents=True, exist_ok=True)
            env = dict(os.environ, ARDUINO_DIRECTORIES_DATA=str(data_dst),
                       ARDUINO_DIRECTORIES_USER=str(root / "arduino-user"))
            sh([cli_dst, "core", "update-index"], env=env)
            sh([cli_dst, "core", "install", "%s@%s" % (CORE_SPEC, args.core_version)], env=env)
        if not args.keep_core:
            prune_arduino_data(data_dst)

    # 3) 源码快照 + 懒人版助手
    src_dst = root / "src" / "GP-Combine"
    print("复制源码快照（%s）→ %s" % (args.src_mode, src_dst))
    copy_snapshot(repo, src_dst, args.src_mode)
    app_dst = root / "app" / "pcapp_dumbversion"
    shutil.rmtree(app_dst, ignore_errors=True)
    copytree(repo / "pcapp_dumbversion", app_dst, skip_names=("__pycache__",))
    write_launchers(root)
    print("✔ 助手 →", app_dst)

    # 4) 可选：pico-sdk（完整版）
    if args.with_pico:
        sdk_src = Path(args.pico_sdk).expanduser()
        if not sdk_src.is_dir():
            raise SystemExit("--with-pico 但找不到 pico-sdk：%s" % sdk_src)
        sdk_dst = root / "tools" / "pico-sdk"
        print("复制 pico-sdk →", sdk_dst)
        copytree(sdk_src, sdk_dst, skip_names=(".git", "build"))

    # 5) 可选：预编译固件
    if args.prebuilt:
        print("编译预编译固件（两版）…")
        build_prebuilt(root, cli_dst, src_dst, root / "work")

    # 6) 清单
    manifest = {
        "name": "GP-Combine 懒人包",
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "platform": sys.platform,
        "arduino_cli": cli_src.name,
        "core": "%s@%s" % (CORE_SPEC, args.core_version),
        "fqbn": FQBN,
        "with_pico_sdk": bool(args.with_pico),
        "prebuilt": bool(args.prebuilt),
        "source_commit": _git_commit(repo),
    }
    (root / "bundle.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    total = count_size(root)
    print("\n=== 懒人包完成 ===")
    print("路径:", root)
    print("大小:", human(total))
    for sub in ("tools", "arduino-data", "src", "app", "firmware"):
        p = root / sub
        if p.exists() and not p.is_symlink():
            print("  %-14s %s" % (sub, human(count_size(p))))
    print("启动:", root / ("Start-GP-Combine.bat" if os.name == "nt" else "start-linux.sh"))

    if args.zip:
        archive = shutil.make_archive(str(root), "zip", root_dir=root.parent, base_dir=root.name)
        print("zip:", archive, human(Path(archive).stat().st_size))
        print("sha256:", sha256(Path(archive)))
    return 0


def _git_commit(repo: Path) -> str:
    try:
        p = subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=10)
        return p.stdout.strip() if p.returncode == 0 else ""
    except Exception:  # noqa: BLE001
        return ""


if __name__ == "__main__":
    raise SystemExit(main())
