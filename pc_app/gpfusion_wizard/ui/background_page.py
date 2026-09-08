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

from ..app_config import (
    BG_ALPHAS,
    local_background_header,
    local_wallpaper_header,
    screen_dims,
)
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
        hint = QLabel("静态背景用图片生成固件背景；动态壁纸用 GIF 作为主界面"
                      "动态背景（此时屏保自动禁用，GIF 需在第 6 步选择）。")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        left.addWidget(hint)
        left.addSpacing(10)

        kind_row = QHBoxLayout()
        kind_row.addWidget(QLabel("背景类型"))
        self.kind_combo = QComboBox()
        self.kind_combo.addItem("静态背景", "static")
        self.kind_combo.addItem("动态壁纸（GIF）", "dynamic")
        self.kind_combo.currentIndexChanged.connect(self._on_kind_changed)
        kind_row.addWidget(self.kind_combo, 1)
        left.addLayout(kind_row)

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
        right = QGroupBox("预览")
        right_l = QVBoxLayout(right)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(240 * 3, 135 * 3)
        self.preview.setStyleSheet(
            "background: #0D1117; border: 1px solid #232C3C; border-radius: 8px;"
        )
        right_l.addWidget(self.preview)
        root.addWidget(right, 3)

    def _load_previous(self) -> None:
        idx = self.kind_combo.findData(self.state.bg_kind)
        if idx >= 0:
            self.kind_combo.blockSignals(True)
            self.kind_combo.setCurrentIndex(idx)
            self.kind_combo.blockSignals(False)
        if self.state.background_src and Path(self.state.background_src).is_file():
            self.path_label.setText(Path(self.state.background_src).name)
        for i, (key, _name) in enumerate(self.MODES):
            if key == self.state.background_mode:
                self.mode_combo.setCurrentIndex(i)
                break
        self._apply_kind_widgets()

    def reload_state(self) -> None:
        self.path_label.setText("未选择图片")
        self._load_previous()
        self._update_preview()
        self.status_label.setText("")

    def _apply_kind_widgets(self) -> None:
        dyn = self.state.bg_kind == "dynamic"
        self.pick_btn.setEnabled(not dyn)
        self.mode_combo.setEnabled(not dyn)
        self.alpha_slider.setEnabled(not dyn)
        self.gen_btn.setText("写入固件设置" if dyn else "生成并写入固件")
        if dyn:
            self.status_label.setText(
                "动态壁纸模式：请在后续 GIF 步骤选择动画；"
                "固件编译后主界面将以 GIF 为背景，屏保自动禁用。"
            )
            self.status_label.setStyleSheet("color: #FFB454;")

    def _on_kind_changed(self) -> None:
        self.state.bg_kind = str(self.kind_combo.currentData())
        self.state.save()
        self._apply_kind_widgets()
        self.generate_now()

    def _write_wallpaper_marker(self) -> None:
        res = self.state.screen_res
        out = local_wallpaper_header(Path(self.state.source_dir), res)
        out.write_text("#pragma once\n#define BG_WALLPAPER 1\n", encoding="utf-8")
        return out

    def _remove_wallpaper_marker(self) -> None:
        res = self.state.screen_res
        out = local_wallpaper_header(Path(self.state.source_dir), res)
        if out.exists():
            out.unlink()

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
        if self.state.bg_kind == "dynamic":
            self.preview.setPixmap(QPixmap())
            self.preview.setText("动态壁纸：主界面以 GIF 动画为背景（屏保禁用）")
            return
        if not self.state.background_src or not Path(self.state.background_src).is_file():
            self.preview.setPixmap(QPixmap())
            return
        mode = self.MODES[self.mode_combo.currentIndex()][0]
        w, h = screen_dims(self.state.screen_res)
        try:
            im = preview_image(self.state.background_src, mode, BG_ALPHAS[idx],
                               size=(w, h))
            qim = QImage(im.tobytes("raw", "RGB"), im.width, im.height,
                         im.width * 3, QImage.Format.Format_RGB888)
            pix = QPixmap.fromImage(qim).scaled(
                w * 3, h * 3,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.preview.setPixmap(pix)
        except Exception as exc:  # noqa: BLE001
            self.preview.setText("无法预览：%s" % exc)

    def generate_now(self) -> None:
        if not self.state.source_dir:
            self.status_label.setText("源码目录未就绪，请先完成第 1 步")
            self.status_label.setStyleSheet("color: #FFB454;")
            return
        try:
            res = self.state.screen_res
            if self.state.bg_kind == "dynamic":
                out = self._write_wallpaper_marker()
                self.status_label.setText(
                    "✔ 动态壁纸已启用（%s）；请在第 6 步选择 GIF 动画"
                    % out
                )
                self.status_label.setStyleSheet("color: #64E0A0;")
                self.changed.emit()
                return
            self._remove_wallpaper_marker()
            src = self.state.background_src
            if not src or not Path(src).is_file():
                self.status_label.setText("请先选择一张背景图片")
                self.status_label.setStyleSheet("color: #FFB454;")
                return
            out = local_background_header(Path(self.state.source_dir), res)
            generate_background_header(src, out, self.state.background_mode,
                                       size=screen_dims(res))
            size_kb = out.stat().st_size // 1024
            self.status_label.setText(
                "✔ 已写入 %s（%d KB，含 5 档透明度）" % (out, size_kb)
            )
            self.status_label.setStyleSheet("color: #64E0A0;")
            self.changed.emit()
        except Exception as exc:  # noqa: BLE001
            self.status_label.setText("生成失败：%s" % exc)
            self.status_label.setStyleSheet("color: #FF7B72;")
