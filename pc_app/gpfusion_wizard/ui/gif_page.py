"""步骤：GIF 动画导入压缩（方案三：RLE 压缩 + 运行时解码）。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..app_config import SCREEN_H, SCREEN_W, local_gif_header
from ..gif_convert import generate_gif_header
from ..wizard_state import WizardState


class GifPage(QWidget):
    changed = Signal()

    MODES = [("cover", "裁切填满"), ("stretch", "拉伸填满"), ("fit", "等比居中")]

    def __init__(self, state: WizardState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._build_ui()
        self._load_previous()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 12)
        left = QVBoxLayout()
        title = QLabel("第 6 步：GIF 动画")
        title.setObjectName("StepTitle")
        left.addWidget(title)
        hint = QLabel("选择 GIF 动画，自动缩放成屏幕分辨率（240×135）并做行程压缩，"
                      "生成固件内的 gif_user.h，机内屏保选择「GIF」即可播放。")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        left.addWidget(hint)
        left.addSpacing(8)

        row = QHBoxLayout()
        self.pick_btn = QPushButton("选择 GIF…")
        self.pick_btn.clicked.connect(self.pick_gif)
        row.addWidget(self.pick_btn)
        row.addWidget(QLabel("缩放"))
        self.mode_combo = QComboBox()
        for key, name in self.MODES:
            self.mode_combo.addItem(name, key)
        self.mode_combo.currentIndexChanged.connect(self._on_change)
        row.addWidget(self.mode_combo)
        row.addWidget(QLabel("调色板"))
        self.palette_combo = QComboBox()
        self.palette_combo.addItem("16 色（更小）", 16)
        self.palette_combo.addItem("32 色（画质更好）", 32)
        self.palette_combo.currentIndexChanged.connect(self._on_change)
        row.addWidget(self.palette_combo)
        left.addLayout(row)

        self.info = QLabel("未选择 GIF")
        self.info.setObjectName("Muted")
        self.info.setWordWrap(True)
        left.addWidget(self.info)

        self.gen_btn = QPushButton("生成并写入固件")
        self.gen_btn.setObjectName("Primary")
        self.gen_btn.clicked.connect(self.generate_now)
        left.addWidget(self.gen_btn)

        self.status = QLabel("")
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)
        left.addWidget(self.status)
        left.addStretch(1)
        root.addLayout(left, 2)

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(SCREEN_W * 3, SCREEN_H * 3)
        self.preview.setStyleSheet(
            "background: #0D1117; border: 1px solid #232C3C; border-radius: 8px;"
        )
        root.addWidget(self.preview, 3)

    def _load_previous(self) -> None:
        if self.state.gif_src and Path(self.state.gif_src).is_file():
            self.info.setText("已选择：%s" % Path(self.state.gif_src).name)
            self._update_preview()

    def reload_state(self) -> None:
        self.info.setText("未选择 GIF")
        for i, (key, _name) in enumerate(self.MODES):
            if key == self.state.gif_mode:
                self.mode_combo.setCurrentIndex(i)
                break
        pi = self.palette_combo.findData(int(self.state.gif_palette))
        if pi >= 0:
            self.palette_combo.setCurrentIndex(pi)
        self._load_previous()
        if not self.state.gif_src or not Path(self.state.gif_src).is_file():
            self.preview.setPixmap(QPixmap())
        self.status.setText("")

    def pick_gif(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 GIF 动画", str(Path.home()), "GIF (*.gif)"
        )
        if not path:
            return
        self.state.gif_src = path
        self.state.save()
        self.info.setText("已选择：%s" % Path(path).name)
        self._update_preview()
        self.generate_now()

    def _on_change(self) -> None:
        self.state.gif_mode = self.MODES[self.mode_combo.currentIndex()][0]
        self.state.gif_palette = int(self.palette_combo.currentData())
        self.state.save()
        self._update_preview()
        self.generate_now()

    def _update_preview(self) -> None:
        if not self.state.gif_src or not Path(self.state.gif_src).is_file():
            self.preview.setPixmap(QPixmap())
            return
        try:
            im = Image.open(self.state.gif_src)
            im.seek(0)
            im2 = im.convert("RGB").resize((SCREEN_W * 3, SCREEN_H * 3), Image.LANCZOS)
            qim = QImage(im2.tobytes("raw", "RGB"), im2.width, im2.height,
                         im2.width * 3, QImage.Format.Format_RGB888)
            self.preview.setPixmap(QPixmap.fromImage(qim))
        except Exception:
            self.preview.clear()

    def generate_now(self) -> None:
        if not self.state.gif_src or not Path(self.state.gif_src).is_file():
            self.status.setText("请先选择 GIF")
            self.status.setStyleSheet("color: #FFB454;")
            return
        if not self.state.source_dir:
            self.status.setText("源码目录未就绪")
            self.status.setStyleSheet("color: #FFB454;")
            return
        try:
            out = local_gif_header(Path(self.state.source_dir))
            out, frames, data_bytes = generate_gif_header(
                self.state.gif_src,
                out,
                self.MODES[self.mode_combo.currentIndex()][0],
                palette_size=int(self.palette_combo.currentData()),
            )
            self.status.setText("✔ 已写入 %s（%d 帧，压缩后 %d KB）"
                                % (out, frames, data_bytes // 1024))
            self.status.setStyleSheet("color: #64E0A0;")
            self.changed.emit()
        except Exception as exc:  # noqa: BLE001
            self.status.setText("生成失败：%s" % exc)
            self.status.setStyleSheet("color: #FF7B72;")
