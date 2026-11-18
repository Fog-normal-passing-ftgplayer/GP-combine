"""固件仿真引擎的 ctypes 封装。

仿真器编成共享库（``libsim240.so`` / ``libsim320.so``），库里面就是**固件本体**：
同一份 ``.ino`` 源码 + 平台垫片。所以这里驱动的不是"模拟画面"，而是真机的菜单状态机 ——
按住 S2 三秒会真的进菜单，方向键会真的翻页。

帧缓冲直接暴露固件的 ``lfb``（RGB565），和 Qt 的 ``Format_RGB565`` 布局一致，零转换。
"""
from __future__ import annotations

import atexit
import ctypes
import itertools
import os
import shutil
import sys
import tempfile
from pathlib import Path

from .app_config import screen_dims

# 与固件一致（esp32_170x320.ino / esp32.ino 的按键位掩码）
BTN_A = 0x0001
BTN_B = 0x0002
BTN_S1 = 0x0100
BTN_S2 = 0x0200
DP_UP = 0x01
DP_DOWN = 0x02
DP_LEFT = 0x04
DP_RIGHT = 0x08


def lib_tag(res: str) -> str:
    """分辨率 → 仿真库短名。170/172 都是 320 宽但各编各的库，不能共用。"""
    res = str(res or "")
    if res == "172x320":
        return "172"
    return "320" if "320" in res else "240"


def find_lib(res: str, source_dir: str | None = None) -> Path | None:
    """找仿真库。

    优先级：环境变量 > 仓库里刚编出来的 build/ > 打包内 bin/ 快照。
    仓库优先很关键：页面上「编译固件并重启预览」会把新库写到 tools/*/build/，
    要是还优先用 bin/ 里 prepare_sim.sh 拷的旧快照，重编就白做了。
    打包成 exe 时仓库路径不存在，自然落到 bin/。
    """
    key = lib_tag(res)
    pkg = Path(__file__).resolve().parent          # .../gpfusion_wizard
    suffix = ".dll" if os.name == "nt" else ".so"
    name = f"libsim{key}{suffix}"

    cands: list[Path] = []
    env = os.environ.get(f"GPFUSION_SIMLIB_{key}")
    if env:
        cands.append(Path(env))

    roots: list[Path] = []
    if source_dir:
        try:
            roots.append(Path(source_dir).expanduser().resolve())
        except OSError:
            pass
    roots.append(pkg.parent.parent)                # 源码运行时：仓库根
    if getattr(sys, "frozen", False):
        roots.append(Path(sys.executable).resolve().parent)
    for root in roots:
        cands.extend(sorted(root.glob(f"tools/*/build/{name}")))

    cands.append(pkg / "bin" / name)               # 打包内快照（最后兜底）

    for c in cands:
        if c.is_file():
            return c
    return None


# dlopen 对「已加载的同路径」会直接复用旧句柄，而 build.sh 是原地覆盖同一个 .so，
# 所以「重新编译后重启预览」会拿到旧代码。每次加载前先复制到唯一路径，绕开这个问题。
_SIM_TMP = Path(tempfile.mkdtemp(prefix="gpsim_"))
atexit.register(shutil.rmtree, _SIM_TMP, ignore_errors=True)
_seq = itertools.count(1)


def _fresh_copy(src: Path) -> Path:
    dst = _SIM_TMP / ("%s_%d%s" % (src.stem, next(_seq), src.suffix))
    shutil.copyfile(src, dst)
    return dst


class SimEngine:
    """一个分辨率对应一个引擎实例（固件的全局变量在库里，两个分辨率各一个库）。"""

    def __init__(self, res: str, fs_root: Path | str) -> None:
        path = find_lib(res)
        if path is None:
            raise FileNotFoundError(
                "找不到仿真库 libsim%s（先跑 tools 下 HEADLESS=1 ./build.sh 或 pc_app/prepare_sim.sh）"
                % lib_tag(res)
            )
        self._lib = ctypes.CDLL(str(_fresh_copy(path)))   # 每次加载独立副本
        lib = self._lib
        lib.sim_boot.argtypes = [ctypes.c_char_p]
        lib.sim_boot.restype = None
        lib.sim_ready.restype = ctypes.c_int
        lib.sim_set_power.argtypes = [ctypes.c_int, ctypes.c_int]
        lib.sim_set_linked.argtypes = [ctypes.c_int]
        lib.sim_redraw.argtypes = []
        lib.sim_width.restype = ctypes.c_int
        lib.sim_height.restype = ctypes.c_int
        lib.sim_tick.argtypes = [ctypes.c_int]
        lib.sim_tick.restype = None
        lib.sim_input.argtypes = [ctypes.c_uint, ctypes.c_uint]
        lib.sim_input.restype = None
        lib.sim_frame.restype = ctypes.c_void_p
        lib.sim_reload_wallpaper.restype = ctypes.c_int
        lib.sim_wallpaper_active.restype = ctypes.c_int

        lib.sim_boot(str(fs_root).encode("utf-8"))
        if not lib.sim_ready():
            raise RuntimeError("仿真引擎初始化失败（lfb 分配失败）")
        self._lib = lib
        # 默认给一份"有电池"的读数：没有它 battPercent 返回 -1，电量图标不画
        self.set_power(3900, False)
        self.set_linked(True)
        self.width = int(lib.sim_width())
        self.height = int(lib.sim_height())
        self.buttons = 0
        self.dpad = 0

    # ---------- 状态 ----------
    @property
    def wallpaper_active(self) -> bool:
        return bool(self._lib.sim_wallpaper_active())

    @property
    def frame_ptr(self) -> int:
        return int(self._lib.sim_frame())

    @property
    def stride(self) -> int:
        return self.width * 2              # RGB565

    # ---------- 驱动 ----------
    def tick(self, ms: int = 16) -> None:
        self._lib.sim_tick(int(ms))

    def set_input(self, buttons: int, dpad: int) -> None:
        if (buttons, dpad) != (self.buttons, self.dpad):
            self.buttons, self.dpad = int(buttons), int(dpad)
        self._lib.sim_input(self.buttons, self.dpad)

    def warm_up(self, ms: int = 5200, step: int = 16) -> None:
        """快进过开机动画。

        固件在开机动画期间（3200ms）会忽略输入，不快进的话用户刚打开预览
        按方向键会被吞掉好几秒，看起来就像"输入没反应"。
        """
        n = max(1, int(ms) // max(1, int(step)))
        for _ in range(n):
            self._lib.sim_tick(int(step))

    def redraw(self) -> None:
        """强制固件重绘一帧（改了注入状态之后立刻反映到预览）。"""
        if self._lib is not None:
            self._lib.sim_redraw()

    def set_power(self, mv: int = 3900, usb: bool = False) -> None:
        """预览用的电量注入：mv<=0 表示没有电池（电量图标不显示）。"""
        if self._lib is not None:
            self._lib.sim_set_power(int(mv), 1 if usb else 0)
            self._lib.sim_redraw()

    def set_linked(self, linked: bool = True) -> None:
        """无线图标是否显示成"已连接"（亮色）；未连接是暗灰，预览里看不清。"""
        if self._lib is not None:
            self._lib.sim_set_linked(1 if linked else 0)
            self._lib.sim_redraw()

    def reload_wallpaper(self) -> bool:
        """壁纸文件换了之后调用，返回是否成功启用。"""
        return bool(self._lib.sim_reload_wallpaper())


def make_fs_root(gfr: Path | None = None, cfg: dict[str, int] | None = None) -> Path:
    """准备一个临时的 LittleFS 根目录：wp/1.gfr + 可选 gpfusion.cfg。

    调用方负责在用完后 ``shutil.rmtree``。
    """
    root = Path(tempfile.mkdtemp(prefix="gpv_"))
    if gfr is not None and Path(gfr).is_file():
        (root / "wp").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(gfr, root / "wp" / "1.gfr")
    if cfg:
        (root / "gpfusion.cfg").write_text(
            "\n".join(f"{k}={int(v)}" for k, v in cfg.items()) + "\n", encoding="utf-8"
        )
    return root
