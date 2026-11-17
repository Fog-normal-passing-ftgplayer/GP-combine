"""仿真器预览页：在生成固件之前，先按按键试一遍真机界面。

背后是仿真库里的**固件本体**，所以看到的就是刷进设备后的样子，
长按、翻页、进子页、返回全走固件自己的状态机。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..app_config import local_wallpaper_gfr, screen_dims
from ..sim_engine import find_lib
from ..wizard_state import WizardState
from .firmware_screen import FirmwareScreen

HOWTO = """仿真库是分开编译的，不需要 ESP32 工具链：

  cd "tools/GP-combine固件彩屏模拟（linux版本）"
  LIB=1 ./build.sh 240      # 或 320
  cd ../../pc_app && ./prepare_sim.sh

注意：改了固件（.ino/.h）之后要先单独重新生成一次 .ino.cpp：

  ./compile_ino.sh 240      # 或 320 / all

否则仿真器会用到旧代码。"""


class SimPage(QWidget):
    def __init__(self, state: WizardState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._auto_started = False
        self._build_ui()

    # ---------- UI ----------
    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 12)

        left = QVBoxLayout()
        title = QLabel("仿真器预览")
        title.setObjectName("StepTitle")
        left.addWidget(title)
        hint = QLabel(
            "这里跑的是固件本体，不是录好的动画。点一下右侧画面拿到键盘焦点，然后：\n"
            "    方向键 = 十字键\n"
            "    1 / 2  = S2 / S1（长按 1 三秒进菜单）\n"
            "    z / x  = A / B\n"
            "可以先在这里确认壁纸、主题、布局的实际效果，满意了再去「编译上传」。"
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        left.addWidget(hint)
        left.addSpacing(10)

        row = QHBoxLayout()
        row.addWidget(QLabel("分辨率"))
        self.res_combo = QComboBox()
        self.res_combo.addItem("240 × 135", "240x135")
        self.res_combo.addItem("170 × 320", "170x320")
        self.res_combo.currentIndexChanged.connect(self._on_res_changed)
        row.addWidget(self.res_combo)
        self.reload_btn = QPushButton("重新加载")
        self.reload_btn.clicked.connect(self.restart)
        row.addWidget(self.reload_btn)
        self.stop_btn = QPushButton("停止")
        self.stop_btn.clicked.connect(self._stop)
        row.addWidget(self.stop_btn)
        row.addStretch(1)
        left.addLayout(row)

        self.info = QLabel("")
        self.info.setObjectName("Muted")
        self.info.setWordWrap(True)
        left.addWidget(self.info)
        left.addStretch(1)

        self.howto_btn = QPushButton("仿真库缺失？查看怎么生成")
        self.howto_btn.setVisible(False)
        self.howto_btn.clicked.connect(self._show_howto)
        left.addWidget(self.howto_btn)

        root.addLayout(left, 2)

        self.screen = FirmwareScreen()
        self.screen.started.connect(self._on_started)
        self.screen.failed.connect(self._on_failed)
        root.addWidget(self.screen, 5)

    # ---------- 生命周期 ----------
    def on_shown(self) -> None:
        """切到本页时自动启动一次（只自动一次，之后由用户控制）。"""
        self.reload_state(force=False)
        if not self.screen.running and not self._auto_started:
            self._auto_started = True
            self._start()

    def reload_state(self, force: bool = True) -> None:
        idx = self.res_combo.findData(self.state.screen_res)
        if idx >= 0 and idx != self.res_combo.currentIndex():
            self.res_combo.blockSignals(True)
            self.res_combo.setCurrentIndex(idx)
            self.res_combo.blockSignals(False)
        if force and self.screen.running:
            self.restart()

    def restart(self) -> None:
        self._start()

    def _stop(self) -> None:
        self.screen.stop()
        self.info.setText("已停止（点「重新加载」恢复）")

    def _start(self) -> None:
        res = str(self.res_combo.currentData() or self.state.screen_res)
        lib = find_lib(res)
        if lib is None:
            self.howto_btn.setVisible(True)
            self.info.setText("找不到仿真库 libsim%s.so —— 真机预览不可用。" % ("320" if "320" in res else "240"))
            return
        self.howto_btn.setVisible(False)

        gfr = None
        if self.state.bg_kind == "dynamic" and self.state.source_dir:
            try:
                cand = local_wallpaper_gfr(Path(self.state.source_dir))
                if cand.is_file():
                    gfr = cand
            except Exception:  # noqa: BLE001
                gfr = None

        cfg = {"layout": int(self.state.default_layout)}
        ok = self.screen.start(res, gfr, cfg=cfg)
        if ok:
            self.screen.setFocus()
            w, h = screen_dims(res)
            src = "卡内壁纸" if gfr else "静态背景（还没生成动态壁纸）"
            self.info.setText("引擎已启动：%dx%d · %s\n库文件：%s" % (w, h, src, lib))

    def _on_res_changed(self) -> None:
        res = str(self.res_combo.currentData())
        self.state.screen_res = res
        self.state.save()
        self.restart()

    def _on_started(self, w: int, h: int) -> None:
        pass    # 信息已在 _start 里写好

    def _on_failed(self, msg: str) -> None:
        self.info.setText("真机预览不可用：%s" % msg)
        self.howto_btn.setVisible(True)

    def _show_howto(self) -> None:
        QMessageBox.information(self, "怎么生成仿真库", HOWTO)
