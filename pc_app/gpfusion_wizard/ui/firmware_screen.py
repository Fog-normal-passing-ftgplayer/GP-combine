"""可交互的固件屏幕控件：把真机画面搬进配置助手，并且能用键盘直接操作。

点一下画面拿到焦点，然后：

    方向键     十字键
    1 / 2      S2 / S1（长按 1 三秒进菜单）
    Z / X      A / B

背后是仿真库里的**固件本体**，所以长按、翻页、进子页、返回全走真机的状态机，
不是回放录好的帧。
"""
from __future__ import annotations

import ctypes
from pathlib import Path

from PySide6.QtCore import QRect, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QKeyEvent, QPainter, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..sim_engine import (
    BTN_A,
    BTN_B,
    BTN_S1,
    BTN_S2,
    DP_DOWN,
    DP_LEFT,
    DP_RIGHT,
    DP_UP,
    SimEngine,
    make_fs_root,
)

# 键盘 → 固件按键
_KEY_BTN = {
    Qt.Key.Key_Z: BTN_A,
    Qt.Key.Key_X: BTN_B,
    Qt.Key.Key_1: BTN_S2,
    Qt.Key.Key_2: BTN_S1,
}
_KEY_DPAD = {
    Qt.Key.Key_Up: DP_UP,
    Qt.Key.Key_Down: DP_DOWN,
    Qt.Key.Key_Left: DP_LEFT,
    Qt.Key.Key_Right: DP_RIGHT,
}


class FirmwareScreen(QWidget):
    """实时显示固件画面，并把键盘事件灌进固件。"""

    started = Signal(int, int)      # 宽, 高
    failed = Signal(str)

    TICK_MS = 16                    # ~60Hz

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(240, 135)
        self.setStyleSheet("background:#0D1117; border:1px solid #232C3C; border-radius:8px;")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._engine: SimEngine | None = None
        self._pix: QPixmap | None = None
        self._held: set[int] = set()
        self._fs_root: Path | None = None
        self._hint = "点一下画面，就能用方向键 / Z / X 直接操作真机菜单"

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(self.TICK_MS)
        self._timer.timeout.connect(self._on_tick)

    # ---------- 生命周期 ----------
    def start(self, res: str, gfr: Path | None = None, cfg: dict[str, int] | None = None) -> bool:
        """启动（或重启）引擎。换了壁纸/分辨率都调用它。"""
        self.stop()
        try:
            self._fs_root = make_fs_root(gfr, cfg)
            self._engine = SimEngine(res, self._fs_root)
        except Exception as exc:                       # noqa: BLE001
            self._engine = None
            self._pix = None
            self._hint = "真机预览不可用：%s" % exc
            self.failed.emit(str(exc))
            self.update()
            return False

        self.setMinimumSize(self._engine.width, self._engine.height)
        self._held.clear()
        self._engine.set_input(0, 0)
        self._engine.warm_up()      # 跳过开机动画（期间固件忽略输入）
        self._timer.start(self.TICK_MS)
        self.started.emit(self._engine.width, self._engine.height)
        self.update()
        return True

    def stop(self) -> None:
        self._timer.stop()
        self._engine = None
        self._pix = None
        self._held.clear()
        if self._fs_root is not None:
            import shutil
            shutil.rmtree(self._fs_root, ignore_errors=True)
            self._fs_root = None

    def reload_wallpaper(self) -> bool:
        return self._engine.reload_wallpaper() if self._engine else False

    @property
    def running(self) -> bool:
        return self._engine is not None

    # ---------- 每帧 ----------
    def _on_tick(self) -> None:
        if self._engine is None:
            return
        try:
            self._engine.tick(self.TICK_MS)
            self._refresh()
        except Exception as exc:                       # noqa: BLE001
            # 出错就停表，别让 60Hz 定时器把 traceback 刷满控制台
            self._timer.stop()
            self._engine = None
            self._hint = "真机预览出错：%s" % exc
            self.failed.emit(str(exc))
            self.update()

    def _refresh(self) -> None:
        w, h = self._engine.width, self._engine.height
        # PySide6 的 QImage 只接受缓冲区、不接受裸指针地址，所以用 ctypes 把 lfb
        # 包成缓冲区（零拷贝）。scaled() 会生成新内存，buf 出了作用域也没关系。
        buf = (ctypes.c_char * (w * h * 2)).from_address(self._engine.frame_ptr)
        img = QImage(buf, w, h, self._engine.stride,
                     QImage.Format.Format_RGB16)   # Format_RGB16 即 RGB565
        scaled = img.scaled(
            self.width(), self.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,     # 最近邻，像素画不糊
        )
        self._pix = QPixmap.fromImage(scaled)
        self.update()

    # ---------- 绘制 ----------
    def paintEvent(self, event) -> None:              # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.GlobalColor.black)
        if self._pix is None or self._pix.isNull():
            p.setPen(Qt.GlobalColor.gray)
            p.drawText(self.rect().adjusted(12, 12, -12, -12),
                       Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self._hint)
            return
        # 居中显示
        x = (self.width() - self._pix.width()) // 2
        y = (self.height() - self._pix.height()) // 2
        p.drawPixmap(QRect(x, y, self._pix.width(), self._pix.height()), self._pix)

    # ---------- 输入 ----------
    def _push_input(self) -> None:
        if self._engine is None:
            return
        buttons = 0
        dpad = 0
        for k in self._held:
            buttons |= _KEY_BTN.get(k, 0)
            dpad |= _KEY_DPAD.get(k, 0)
        self._engine.set_input(buttons, dpad)

    def keyPressEvent(self, event: QKeyEvent) -> None:      # noqa: N802
        k = event.key()
        if k in _KEY_BTN or k in _KEY_DPAD:
            self._held.add(k)
            self._push_input()
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:    # noqa: N802
        k = event.key()
        if k in _KEY_BTN or k in _KEY_DPAD:
            # 自动重复的 release 事件要忽略，否则按住方向键会变成连点
            if not event.isAutoRepeat():
                self._held.discard(k)
                self._push_input()
            event.accept()
            return
        super().keyReleaseEvent(event)

    def mousePressEvent(self, event) -> None:               # noqa: N802
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        super().mousePressEvent(event)

    def focusOutEvent(self, event) -> None:                 # noqa: N802
        # 失焦时松开所有按键，避免卡住
        self._held.clear()
        self._push_input()
        super().focusOutEvent(event)
