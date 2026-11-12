"""固件真实画面预览：调仿真器导出主界面帧，按 .gfr 的帧延迟循环播放。

和 ``gif_page._update_preview()`` 里"把 GIF 缩放显示"不同，这里显示的是**固件渲染层
输出的真实画面** —— 状态栏、按键布局、主题、壁纸叠加全都是真机那份代码画出来的，
也就是刷进设备后会看到的同一份像素。

仿真器以 headless 构建（``build/sim240`` / ``build/sim320``）跑，不需要图形环境。
"""
from __future__ import annotations

import os
import shutil
import struct
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QWidget

from ..app_config import screen_dims
from ..jobs import JobRunner


def preview_enabled() -> bool:
    """真机预览总开关：设 GPFUSION_NO_PREVIEW=1 可关闭（打包环境跑不了仿真器时用）。"""
    return os.environ.get("GPFUSION_NO_PREVIEW", "").strip().lower() not in ("1", "true", "yes", "on")


def find_sim(res: str) -> Path | None:
    """找仿真器可执行文件。优先级：环境变量 > 打包内 bin/ > 仓库 tools/ 下。"""
    key = "320" if "320" in str(res) else "240"
    pkg = Path(__file__).resolve().parent.parent          # .../gpfusion_wizard
    cands: list[Path] = []
    env = os.environ.get(f"GPFUSION_SIM_{key}")
    if env:
        cands.append(Path(env))
    cands.append(pkg / "bin" / f"sim{key}")               # PyInstaller 打包位置
    repo = pkg.parent.parent                              # 仓库根
    cands.extend(sorted(repo.glob(f"tools/*/build/sim{key}")))   # 开发态
    for c in cands:
        if not c.is_file():
            continue
        if not os.access(c, os.X_OK):
            # 打包/解压后可能丢执行位，补一下再判断
            try:
                c.chmod(c.stat().st_mode | 0o111)
            except OSError:
                continue
        if os.access(c, os.X_OK):
            return c
    return None


def read_gfr_delays(path: Path) -> list[int]:
    """读 .gfr 的每帧时长（毫秒）。格式见固件 gifLoadFromFs()。"""
    try:
        d = path.read_bytes()
        if len(d) < 16 or d[:4] != b"GFR1" or d[4] != 2:
            return []
        frames = struct.unpack_from("<H", d, 5)[0]
        pal = d[11]
        off = 16 + 2 * pal
        if frames <= 0 or len(d) < off + 2 * frames:
            return []
        return [struct.unpack_from("<H", d, off + 2 * i)[0] for i in range(frames)]
    except OSError:
        return []


class FirmwarePreview(QLabel):
    """循环播放仿真器导出的帧；失败时保持静态占位图。"""

    ready = Signal(int)      # 帧数
    failed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._next)
        self._pix: list[QPixmap] = []
        self._delays: list[int] = []
        self._idx = 0
        self._runner: JobRunner | None = None
        self._gen = 0                 # 并发保护：只认最后一次请求的结果
        self._tmp: Path | None = None

    # ---------- 对外 ----------
    def show_static(self, pix: QPixmap | None) -> None:
        """立即可用的占位图（原始 GIF 缩放），帧导好之前先给个反馈。"""
        self.stop()
        self.setPixmap(pix if pix else QPixmap())

    def set_pending(self, text: str = "正在生成真机预览…") -> None:
        self.stop()
        self.clear()
        self.setText(text)
        self.setStyleSheet(
            "background:#0D1117; border:1px solid #232C3C; border-radius:8px;"
            "color:#8B96A8; font-size:13px;"
        )

    def play(
        self,
        res: str,
        gfr: Path | None,
        cfg: dict[str, int] | None = None,
        scale: int = 3,
        count: int = 60,
    ) -> bool:
        """启动一次预览。返回 False 表示环境不满足（找不到仿真器等），调用方可忽略。"""
        if not preview_enabled():
            return False
        self._gen += 1
        gen = self._gen
        self.stop()

        w, h = screen_dims(res)
        sim = find_sim(res)
        if sim is None:
            self.failed.emit("未找到仿真器 sim%s（见 firmware_preview.find_sim）" % ("320" if w == 320 else "240"))
            return False
        if gfr is None or not Path(gfr).is_file():
            self.failed.emit("还没有生成卡内壁纸 /wp/1.gfr")
            return False

        tmp = Path(tempfile.mkdtemp(prefix="gpv_"))
        self._tmp = tmp
        # 仿真器把设备路径映射到这个目录：/wp/1.gfr、/gpfusion.cfg
        (tmp / "wp").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(gfr, tmp / "wp" / "1.gfr")
        if cfg:
            (tmp / "gpfusion.cfg").write_text(
                "\n".join(f"{k}={int(v)}" for k, v in cfg.items()) + "\n", encoding="utf-8"
            )
        out = tmp / "frames"

        # 按 .gfr 的真实帧数导出，避免循环动画被录成好几圈（20 帧的 GIF 不该存 60 张）
        delays = read_gfr_delays(tmp / "wp" / "1.gfr")
        if delays:
            count = max(1, min(int(count), len(delays)))

        self.set_pending("正在生成真机预览…")
        runner = JobRunner()
        self._runner = runner
        runner.finished.connect(lambda code: self._on_finished(gen, code, tmp, out, w, h, scale))
        runner.start([
            str(sim), "--mode=wallpaper",
            f"--out={out}", f"--count={count}", f"--fs={tmp}",
        ])
        return True

    def stop(self) -> None:
        self._timer.stop()
        self._pix = []
        self._delays = []
        self._idx = 0
        if self._tmp and self._tmp.exists():
            shutil.rmtree(self._tmp, ignore_errors=True)
        self._tmp = None

    # ---------- 内部 ----------
    def _on_finished(self, gen: int, code: int, tmp: Path, out: Path, w: int, h: int, scale: int) -> None:
        if gen != self._gen:
            return                                  # 已有更新的请求，丢弃这次结果
        pngs = sorted(out.glob("w*.png")) if out.is_dir() else []
        if code != 0 or not pngs:
            self.set_pending("真机预览生成失败（退出码 %d）" % code)
            self.failed.emit("仿真器退出码 %d" % code)
            shutil.rmtree(tmp, ignore_errors=True)
            if self._tmp == tmp:
                self._tmp = None
            return

        self._pix = [
            QPixmap(str(p)).scaled(
                w * scale, h * scale,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,   # 最近邻，像素画不糊
            )
            for p in pngs
        ]
        self._delays = read_gfr_delays(tmp / "wp" / "1.gfr") or [50] * len(self._pix)
        # 帧已进内存，临时目录可以立刻删掉
        shutil.rmtree(tmp, ignore_errors=True)
        if self._tmp == tmp:
            self._tmp = None

        self.setStyleSheet("")                       # 去掉占位文字样式
        self._idx = 0
        self.setPixmap(self._pix[0])
        self._timer.start(max(20, self._delays[0] if self._delays else 50))
        self.ready.emit(len(self._pix))

    def _next(self) -> None:
        if not self._pix:
            self._timer.stop()
            return
        self._idx = (self._idx + 1) % len(self._pix)
        self.setPixmap(self._pix[self._idx])
        d = self._delays[self._idx % len(self._delays)] if self._delays else 50
        self._timer.start(max(20, d))
