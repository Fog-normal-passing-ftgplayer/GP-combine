"""懒人包环境探测与初始化。

懒人包的目录约定（把自己当成一个绿色软件）：

    <包根>/
      app/            pcapp_dumbversion（本程序）
      tools/          arduino-cli/（必需）、pico-sdk/（完整版才有）
      arduino-data/   ARDUINO_DIRECTORIES_DATA（内置 esp32 core + 工具链）
      arduino-user/   ARDUINO_DIRECTORIES_USER
      src/GP-Combine/ 源码快照
      firmware/       预编译固件（可选）
      work/           运行时生成（构建产物 / 卡内文件镜像）

开发模式下（直接跑仓库里的这份代码）会退回到仓库根 + ~/.arduino15，
这样同一个程序既能当懒人包用，也能在开发机上调试。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# 包根标志：完整懒人包有 arduino-data；Win7 刷机包没有（只有 bundle.json）
BUNDLE_MARKERS = ("arduino-data", "bundle.json")
CLI_RELATIVE = Path("tools") / "arduino-cli"


@dataclass
class Env:
    """运行环境信息（UI 只读展示，pipeline 使用）。"""

    root: Path
    portable: bool = False                 # True = 跑在懒人包里
    cli: Path | None = None
    cli_version: str = ""
    arduino_data: Path | None = None
    arduino_user: Path | None = None
    source_dir: Path | None = None
    sketch_240: Path | None = None
    sketch_320: Path | None = None
    pc_app_dir: Path | None = None         # 复用 pc_app 的转换/打包代码
    firmware_dir: Path | None = None
    work_dir: Path | None = None
    pico_sdk: Path | None = None
    core_versions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def core_ok(self) -> bool:
        return any(v.startswith("esp32:esp32") for v in self.core_versions)

    def sketch(self, res: str) -> Path | None:
        return self.sketch_320 if res == "170x320" else self.sketch_240


def _cli_name() -> str:
    return "arduino-cli.exe" if os.name == "nt" else "arduino-cli"


def find_bundle_root(explicit: str | Path | None = None) -> Path | None:
    """从显式参数 / 环境变量 / 自身位置 / 当前目录往上找包根。"""
    seeds: list[Path] = []
    if explicit:
        seeds.append(Path(explicit).expanduser())
    env_root = os.environ.get("GPCOMBINE_BUNDLE")
    if env_root:
        seeds.append(Path(env_root).expanduser())
    here = Path(__file__).resolve()
    seeds += [here.parent, here.parent.parent, here.parent.parent.parent]
    # 打包成 exe 后（PyInstaller），从可执行文件位置往上找
    exe = Path(sys.executable).resolve()
    if exe.parent.name.lower() not in ("python", "bin", "scripts"):
        seeds.append(exe.parent)
    seeds.append(Path.cwd())
    seen: set[Path] = set()
    for seed in seeds:
        for cand in (seed, *seed.parents):
            if cand in seen:
                continue
            seen.add(cand)
            if any((cand / m).exists() for m in BUNDLE_MARKERS):
                return cand
    return None


def _find_cli(root: Path | None) -> Path | None:
    if root is not None:
        cand = root / CLI_RELATIVE / _cli_name()
        if cand.is_file():
            return cand
        # 允许 tools/arduino-cli 直接放二进制
        cand2 = root / "tools" / _cli_name()
        if cand2.is_file():
            return cand2
    found = shutil.which("arduino-cli")
    return Path(found) if found else None


def _repo_root() -> Path:
    """开发模式下的仓库根（本文件的上上级）。"""
    return Path(__file__).resolve().parents[2]


def _default_arduino15() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Arduino15"
    return Path.home() / ".arduino15"


def init(explicit_root: str | Path | None = None) -> Env:
    """探测环境并把必要变量写进 os.environ（子进程会自动继承）。"""
    bundle = find_bundle_root(explicit_root)
    env = Env(root=bundle or _repo_root(), portable=bundle is not None)

    if env.portable:
        data = env.root / "arduino-data"
        if not data.is_dir():
            # Win7 刷机包没有 core：建个空目录占位，保证环境变量/配置合法
            data.mkdir(parents=True, exist_ok=True)
            env.notes.append("没有内置 arduino-data（只支持刷预编译固件）")
        env.arduino_data = data
        env.arduino_user = env.root / "arduino-user"
        env.work_dir = env.root / "work"
        src = env.root / "src" / "GP-Combine"
        env.source_dir = src if src.is_dir() else (env.root / "src")
        env.firmware_dir = env.root / "firmware"
        sdk = env.root / "tools" / "pico-sdk"
        if sdk.is_dir():
            env.pico_sdk = sdk
    else:
        env.source_dir = env.root
        env.arduino_data = Path(
            os.environ.get("ARDUINO_DIRECTORIES_DATA") or _default_arduino15()
        )
        env.arduino_user = Path(
            os.environ.get("ARDUINO_DIRECTORIES_USER")
            or (env.root / ".dumbwork" / "arduino-user")
        )
        env.firmware_dir = env.root
        env.work_dir = env.root / ".dumbwork"
        env.notes.append("开发模式：使用系统 arduino-cli / 用户目录")

    env.work_dir.mkdir(parents=True, exist_ok=True)
    env.arduino_user.mkdir(parents=True, exist_ok=True)

    # arduino-cli 认这三个环境变量，子进程继承后就用包内的 core，不碰用户目录
    os.environ["ARDUINO_DIRECTORIES_DATA"] = str(env.arduino_data)
    os.environ["ARDUINO_DIRECTORIES_USER"] = str(env.arduino_user)
    # 离线运行时别让 arduino-cli 去联网检查更新（否则可能卡在超时）
    os.environ["ARDUINO_UPDATER_ENABLE_NOTIFICATION"] = "false"
    os.environ.setdefault("NO_PROXY", "*")
    if env.pico_sdk:
        os.environ["PICO_SDK_PATH"] = str(env.pico_sdk)

    if env.portable:
        cfg = env.root / "arduino-cli.yaml"
        try:
            cfg.write_text(
                "directories:\n"
                "  data: %s\n"
                "  user: %s\n"
                "  downloads: %s\n"
                "updater:\n"
                "  enable_notification: false\n"
                % (env.arduino_data, env.arduino_user, env.root / "work" / "downloads"),
                encoding="utf-8",
            )
            os.environ["ARDUINO_CONFIG_FILE"] = str(cfg)
            (env.root / "work" / "downloads").mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            env.notes.append("写 arduino-cli.yaml 失败：%s" % exc)

    env.cli = _find_cli(env.root if env.portable else None)
    if env.cli and env.portable:
        # 让 pc_app 里 shutil.which("arduino-cli") 也能命中包内的那份
        cli_dir = str(env.cli.parent)
        if cli_dir not in os.environ.get("PATH", "").split(os.pathsep):
            os.environ["PATH"] = cli_dir + os.pathsep + os.environ.get("PATH", "")

    if env.source_dir:
        env.sketch_240 = env.source_dir / "esp32"
        env.sketch_320 = env.source_dir / "esp32_170x320"
        pc_app = env.source_dir / "pc_app"
        if pc_app.is_dir():
            env.pc_app_dir = pc_app
    if env.pc_app_dir.is_dir() if env.pc_app_dir else False:
        if str(env.pc_app_dir) not in sys.path:
            sys.path.insert(0, str(env.pc_app_dir))

    return env


def patch_pc_app_paths(env: Env) -> None:
    """把 pc_app 里写死的 ~/.arduino15 指到包内（mklittlefs / esptool 在包内）。"""
    try:
        from gpfusion_wizard import wallpaper_fs  # type: ignore
    except Exception as exc:  # pragma: no cover - 只有包不完整才会走到
        env.notes.append("pc_app 模块不可用：%s" % exc)
        return
    if env.arduino_data:
        wallpaper_fs._arduino15 = lambda: env.arduino_data  # type: ignore[attr-defined]
    else:
        env.arduino_data = env.root / "arduino-data"
    # Win7 刷机包没有 arduino-data：用当前解释器里的 esptool 模块刷写
    bundled_esptool = env.arduino_data / "packages" / "esp32" / "tools" / "esptool_py"
    if not bundled_esptool.is_dir():
        try:
            import esptool  # noqa: F401
        except Exception:  # noqa: BLE001
            return
        wallpaper_fs.find_esptool = lambda: [sys.executable, "-m", "esptool"]  # type: ignore[assignment]


def _run(cmd: list[str], timeout: int = 120) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return 127, "找不到命令：%s" % cmd[0]
    except subprocess.TimeoutExpired:
        return 124, "超时：%s" % " ".join(cmd)


def refresh_core_list(env: Env) -> None:
    """读取包内已安装的 core 列表。"""
    env.core_versions = []
    if not env.cli:
        return
    code, out = _run([str(env.cli), "core", "list"])
    if code != 0:
        env.notes.append("core list 失败：%s" % out.strip().splitlines()[-1:])
        return
    for line in out.splitlines()[1:]:
        parts = line.split()
        # 只认 "包名:平台 版本 …" 这种行，忽略 Error / 表头等噪音
        if len(parts) >= 2 and parts[0].count(":") == 1 and not parts[0].startswith("ID"):
            env.core_versions.append("%s %s" % (parts[0], parts[1]))


def refresh_cli_version(env: Env) -> None:
    if not env.cli:
        return
    code, out = _run([str(env.cli), "version"])
    if code == 0:
        env.cli_version = out.strip().splitlines()[0] if out.strip() else ""


def selftest(env: Env) -> int:
    """命令行自检：确认包是否完整、能否离线编译。"""
    refresh_cli_version(env)
    refresh_core_list(env)
    print("模式      :", "懒人包（离线）" if env.portable else "开发模式")
    print("包根      :", env.root)
    print("arduino-cli:", env.cli or "✘ 未找到", env.cli_version)
    print("arduino-data:", env.arduino_data)
    print("core      :", ", ".join(env.core_versions) or "✘ 未安装")
    print("源码      :", env.source_dir)
    print("  esp32      :", "✔" if env.sketch_240 and env.sketch_240.is_dir() else "✘")
    print("  esp32_170x320:", "✔" if env.sketch_320 and env.sketch_320.is_dir() else "✘")
    print("pc_app    :", env.pc_app_dir or "✘ 未找到")
    print("工作目录  :", env.work_dir)
    print("预编译固件:", env.firmware_dir if env.firmware_dir and env.firmware_dir.is_dir() else "-")
    print("pico-sdk  :", env.pico_sdk or "-（基础版不含，Pico 侧用预编译 UF2）")
    for note in env.notes:
        print("注意      :", note)

    ok = bool(env.cli and env.core_ok and env.sketch_240 and env.sketch_320)
    fw_dir = env.firmware_dir
    has_fw = bool(fw_dir and fw_dir.is_dir() and any(fw_dir.glob("esp32_*/app.bin")))
    if ok:
        print("结论      : ✔ 离线可用（可编译 + 可刷写）")
        return 0
    if has_fw:
        print("结论      : ✔ 只支持刷预编译固件（Win7 刷机包形态，编译请用完整包）")
        return 0
    print("结论      : ✘ 包不完整")
    return 1
