"""步骤 1：背景图选择、预览与生成 background.h。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..app_config import BG_ALPHAS, SCREEN_H, SCREEN_W, local_background_header
from ..imagegen import generate_background_header, preview_image
from ..wizard_state import WizardState


class BackgroundPage(QWidget):
    changed = Signal()

    MODES = [("cover", "裁切填满（推荐）"), ("stretch", "拉伸填满"), ("fit", "等比居中")]

    def __init__(self, state: WizardState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._build_ui()
        self._load_previous()
        self._update_preview()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 12)

        # 左列：控制
        left = QVBoxLayout()
        title = QLabel("第 3 步：背景图")
        title.setObjectName("StepTitle")
        left.addWidget(title)
        hint = QLabel("选择一张图片，会自动转换成屏幕分辨率（240×135），"
                      "生成固件内的 5 档透明度背景。")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        left.addWidget(hint)
        left.addSpacing(10)

        pick_row = QHBoxLayout()
        self.pick_btn = QPushButton("选择图片…")
        self.pick_btn.clicked.connect(self.pick_image)
        pick_row.addWidget(self.pick_btn)
        left.addLayout(pick_row)

        self.path_label = QLabel("未选择图片")
        self.path_label.setObjectName("Muted")
        self.path_label.setWordWrap(True)
        left.addWidget(self.path_label)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("缩放方式"))
        self.mode_combo = QComboBox()
        for key, name in self.MODES:
            self.mode_combo.addItem(name, key)
        self.mode_combo.currentIndexChanged.connect(self._on_change)
        mode_row.addWidget(self.mode_combo, 1)
        left.addLayout(mode_row)

        alpha_row = QHBoxLayout()
        alpha_row.addWidget(QLabel("预览透明度"))
        self.alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.alpha_slider.setRange(1, len(BG_ALPHAS))
        self.alpha_slider.setValue(3)
        self.alpha_slider.valueChanged.connect(self._update_preview)
        alpha_row.addWidget(self.alpha_slider, 1)
        self.alpha_label = QLabel("55%")
        self.alpha_label.setMinimumWidth(42)
        alpha_row.addWidget(self.alpha_label)
        left.addLayout(alpha_row)

        left.addSpacing(8)
        gen_row = QHBoxLayout()
        self.gen_btn = QPushButton("生成并写入固件")
        self.gen_btn.setObjectName("Primary")
        self.gen_btn.clicked.connect(self.generate_now)
        gen_row.addWidget(self.gen_btn)
        left.addLayout(gen_row)

        self.status_label = QLabel("")
        self.status_label.setObjectName("Muted")
        self.status_label.setWordWrap(True)
        left.addWidget(self.status_label)
        left.addStretch(1)
        root.addLayout(left, 2)

        # 右列：预览
        right = QGroupBox("预览（240×135 内容区）")
        right_l = QVBoxLayout(right)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(SCREEN_W * 3, SCREEN_H * 3)
        self.preview.setStyleSheet(
            "background: #0D1117; border: 1px solid #232C3C; border-radius: 8px;"
        )
        right_l.addWidget(self.preview)
        root.addWidget(right, 3)

    def _load_previous(self) -> None:
        if self.state.background_src and Path(self.state.background_src).is_file():
            self.path_label.setText(Path(self.state.background_src).name)
        for i, (key, _name) in enumerate(self.MODES):
            if key == self.state.background_mode:
                self.mode_combo.setCurrentIndex(i)
                break

    def reload_state(self) -> None:
        self.path_label.setText("未选择图片")
        self._load_previous()
        self._update_preview()
        self.status_label.setText("")

    def _on_change(self) -> None:
        self.state.background_mode = self.MODES[self.mode_combo.currentIndex()][0]
        self.state.save()
        self._update_preview()
        self.generate_now()

    def pick_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择背景图片",
            str(Path.home()),
            "图片 (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if not path:
            return
        self.state.background_src = path
        self.path_label.setText(Path(path).name)
        self.state.save()
        self._update_preview()
        self.generate_now()

    def _update_preview(self) -> None:
        idx = self.alpha_slider.value() - 1
        self.alpha_label.setText("%d%%" % int(BG_ALPHAS[idx] * 100))
        if not self.state.background_src or not Path(self.state.background_src).is_file():
            self.preview.setPixmap(QPixmap())
            return
        mode = self.MODES[self.mode_combo.currentIndex()][0]
        try:
            im = preview_image(self.state.background_src, mode, BG_ALPHAS[idx])
            qim = QImage(im.tobytes("raw", "RGB"), im.width, im.height,
                         im.width * 3, QImage.Format.Format_RGB888)
            pix = QPixmap.fromImage(qim).scaled(
                SCREEN_W * 3, SCREEN_H * 3,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.preview.setPixmap(pix)
        except Exception as exc:  # noqa: BLE001
            self.preview.setText("无法预览：%s" % exc)

    def generate_now(self) -> None:
        src = self.state.background_src
        if not src or not Path(src).is_file():
            self.status_label.setText("请先选择一张背景图片")
            self.status_label.setStyleSheet("color: #FFB454;")
            return
        if not self.state.source_dir:
            self.status_label.setText("源码目录未就绪，请先完成第 1 步")
            self.status_label.setStyleSheet("color: #FFB454;")
            return
        try:
            out = local_background_header(Path(self.state.source_dir))
            generate_background_header(src, out, self.state.background_mode)
            size_kb = out.stat().st_size // 1024
            self.status_label.setText(
                "✔ 已写入 %s（%d KB，含 5 档透明度）" % (out, size_kb)
            )
            self.status_label.setStyleSheet("color: #64E0A0;")
            self.changed.emit()
        except Exception as exc:  # noqa: BLE001
            self.status_label.setText("生成失败：%s" % exc)
            self.status_label.setStyleSheet("color: #FF7B72;")
