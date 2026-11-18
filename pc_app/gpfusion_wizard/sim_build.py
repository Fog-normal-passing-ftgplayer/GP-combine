"""在配置助手里重新生成 .ino.cpp 并重编仿真库，让预览跟上固件改动。

为什么需要单独两步：
- 生成 `.ino.cpp`（arduino-cli）要跑 ESP32 工具链，几分钟；
- 编仿真库只要几秒。
合在一起的话改一行仿真器代码也要等工具链，所以这里分开跑，
跑完再重启引擎，预览就是最新固件了。
"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from .jobs import JobRunner
from .sim_engine import lib_tag


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def find_sim_dir() -> Path | None:
    """定位仿真器源码目录（含 sim_main.cpp 与构建脚本）。"""
    repo = repo_root()
    dirs: list[Path] = []
    for pat in ("*/sim_main.cpp", "tools/*/sim_main.cpp"):
        for p in sorted(repo.glob(pat)):
            if p.is_file() and p.parent not in dirs:
                dirs.append(p.parent)
    if not dirs:
        return None
    # 优先挑支持共享库（配置助手预览要用）的那个
    for d in dirs:
        if _supports_lib(d):
            return d
    return dirs[0]


def _supports_lib(d: Path) -> bool:
    """构建脚本是否真的能产出共享库（配置助手预览要用 SIM_LIB / libsim*）。"""
    name = "build.bat" if os.name == "nt" else "build.sh"
    script = d / name
    try:
        return script.is_file() and "SIM_LIB" in script.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False


def build_plan(res: str) -> list[dict] | None:
    """依次要跑的命令：[{label, cmd, env}]；None = 找不到仿真器目录。"""
    d = find_sim_dir()
    if d is None or not _supports_lib(d):
        return None
    tag = lib_tag(res)
    if os.name == "nt":
        ini, lib = d / "compile_ino.bat", d / "build.bat"
        if not (ini.is_file() and lib.is_file()):
            return None
        return [
            {"label": "生成 .ino.cpp（arduino-cli，几分钟）",
             "cmd": ["cmd", "/c", str(ini), tag], "env": None},
            {"label": "编译仿真库",
             "cmd": ["cmd", "/c", str(lib), tag], "env": {"LIB": "1"}},
        ]
    ini, lib = d / "compile_ino.sh", d / "build.sh"
    if not (ini.is_file() and lib.is_file()):
        return None
    return [
        {"label": "生成 .ino.cpp（arduino-cli，几分钟）",
         "cmd": ["bash", str(ini), tag], "env": None},
        {"label": "编译仿真库",
         "cmd": ["bash", str(lib), tag], "env": {"LIB": "1"}},
    ]


class SimBuilder(QObject):
    """按顺序执行 build_plan，把每行输出转发给界面。"""

    log = Signal(str)
    step = Signal(int, int, str)        # 当前步, 总步数, 说明
    finished = Signal(bool)

    def __init__(self, plan: list[dict], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._plan = plan
        self._runner: JobRunner | None = None
        self._i = 0
        self._ok = True

    def start(self) -> None:
        self._run_next()

    def _run_next(self) -> None:
        if not self._ok or self._i >= len(self._plan):
            self.finished.emit(self._ok and self._i >= len(self._plan))
            return

        item = self._plan[self._i]
        self.step.emit(self._i + 1, len(self._plan), item["label"])
        self.log.emit("── [%d/%d] %s" % (self._i + 1, len(self._plan), item["label"]))

        env = dict(os.environ)
        if item.get("env"):
            env.update({k: str(v) for k, v in item["env"].items()})

        runner = JobRunner()              # JobRunner 不接受 parent
        self._runner = runner             # 持有引用，避免被 GC 回收
        runner.line_ready.connect(self.log.emit)
        runner.finished.connect(self._on_step_done)
        runner.start(item["cmd"], env=env)

    def _on_step_done(self, code: int) -> None:
        if code != 0:
            self._ok = False
            self.log.emit("✘ 命令失败（退出码 %d）" % code)
            self.finished.emit(False)
            return
        self._i += 1
        self._run_next()
