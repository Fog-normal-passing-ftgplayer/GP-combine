"""固件仿真引擎的 ctypes 封装。

仿真器编成共享库（``libsim240.so`` / ``libsim320.so``），库里面就是**固件本体**：
同一份 ``.ino`` 源码 + 平台垫片。所以这里驱动的不是"模拟画面"，而是真机的菜单状态机 ——
按住 S2 三秒会真的进菜单，方向键会真的翻页。

帧缓冲直接暴露固件的 ``lfb``（RGB565），和 Qt 的 ``Format_RGB565`` 布局一致，零转换。
"""
from __future__ import annotations

import ctypes
import os
import shutil
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


def find_lib(res: str) -> Path | None:
    """找仿真库。优先级：环境变量 > 打包内 bin/ > 仓库 tools/ 下。"""
    key = "320" if "320" in str(res) else "240"
    pkg = Path(__file__).resolve().parent          # .../gpfusion_wizard
    cands: list[Path] = []
    env = os.environ.get(f"GPFUSION_SIMLIB_{key}")
    if env:
        cands.append(Path(env))
    suffix = ".dll" if os.name == "nt" else ".so"
    cands.append(pkg / "bin" / f"libsim{key}{suffix}")
    repo = pkg.parent.parent
    cands.extend(sorted(repo.glob(f"tools/*/build/libsim{key}{suffix}")))
    for c in cands:
        if c.is_file():
            return c
    return None


class SimEngine:
    """一个分辨率对应一个引擎实例（固件的全局变量在库里，两个分辨率各一个库）。"""

    def __init__(self, res: str, fs_root: Path | str) -> None:
        path = find_lib(res)
        if path is None:
            raise FileNotFoundError(
                "找不到仿真库 libsim%s（先跑 tools 下 HEADLESS=1 ./build.sh 或 pc_app/prepare_sim.sh）"
                % ("320" if "320" in str(res) else "240")
            )
        self._lib = ctypes.CDLL(str(path))
        lib = self._lib
        lib.sim_boot.argtypes = [ctypes.c_char_p]
        lib.sim_boot.restype = None
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
