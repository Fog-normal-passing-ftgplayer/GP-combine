"""步骤 2：按键布局可视化编辑器，实时写 layout_user.h。

编辑的是机内第 4 个「自定义」布局：4 个移动键 + 右侧按键 + 可选街机摇杆。
"""
from __future__ import annotations

import statistics
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..app_config import (
    local_defaults_header,
    local_layout_header,
    screen_dims,
)
from ..defaults_header import write_defaults_header
from ..lite_layout_header import (
    generate_lite_layout_header,
    write_lite_layout_header,
)
from ..layout_header import write_layout_header
from ..layout_model import (
    GROUP_CLUSTER,
    GROUP_LEVER,
    GROUP_MOVE,
    LITE_SCREEN,
    LITE_STATUS_H,
    Btn,
    Layout,
    find_free_spot,
    sanitize_layout,
)
from ..wizard_state import WizardState
from .add_button_dialog import AddButtonDialog
from .layout_canvas import LayoutCanvas


class LayoutPage(QWidget):
    changed = Signal()

    def __init__(
        self,
        state: WizardState,
        parent: QWidget | None = None,
        lite: bool = False,
    ) -> None:
        super().__init__(parent)
        self.state = state
        self.lite = lite
        self._build_ui()
        self._sync_from_state()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 12)

        # 左列：画布
        left = QVBoxLayout()
        title = QLabel("按键布局（自定义）")
        title.setObjectName("StepTitle")
        left.addWidget(title)
        hint = QLabel("在这里设计的布局对应机内第 4 个「自定义」布局选项。"
                      "拖动任意按键调整位置，右侧面板可改文字/大小/形状，"
                      "任意按键都能删除，改动实时写入固件源文件。")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        left.addWidget(hint)
        left.addSpacing(8)

        default_row = QHBoxLayout()
        default_row.addWidget(QLabel("默认布局"))
        self.default_combo = QComboBox()
        for name, val in (("街机", 0), ("HITBOX", 1), ("WASD", 2), ("自定义", 3)):
            self.default_combo.addItem(name, val)
        self.default_combo.currentIndexChanged.connect(self._on_default_changed)
        default_row.addWidget(self.default_combo, 1)
        hint2 = QLabel("机内上电后默认选中的布局")
        hint2.setObjectName("Muted")
        default_row.addWidget(hint2)
        left.addLayout(default_row)

        lw, lh, status_h = self._dims()

        toolbar = QHBoxLayout()
        self.lever_check = QCheckBox("显示街机摇杆")
        self.lever_check.toggled.connect(self._on_lever_toggled)
        toolbar.addWidget(self.lever_check)
        toolbar.addSpacing(12)
        toolbar.addWidget(QLabel("全局大小"))
        self.global_size = QSlider(Qt.Orientation.Horizontal)
        self.global_size.setMinimumWidth(110)
        self.global_size.setRange(3, max(3, self._global_r_max()))
        self.global_size.valueChanged.connect(self._on_global_size_preview)
        self.global_size.sliderReleased.connect(self._on_global_size_committed)
        toolbar.addWidget(self.global_size, 1)
        self.global_size_value = QLabel("--")
        self.global_size_value.setMinimumWidth(28)
        toolbar.addWidget(self.global_size_value)
        self.lever_scale_check = QCheckBox("同时缩放摇杆")
        self.lever_scale_check.setChecked(True)
        toolbar.addWidget(self.lever_scale_check)
        toolbar.addStretch(1)
        self.reset_btn = QPushButton("恢复默认")
        self.reset_btn.clicked.connect(self.reset_defaults)
        toolbar.addWidget(self.reset_btn)
        left.addLayout(toolbar)

        self.canvas = LayoutCanvas(logical_size=(lw, lh), status_h=status_h)
        self.canvas.item_moved.connect(self._on_item_moved)
        self.canvas.lever_moved.connect(self._on_lever_moved)
        self.canvas.item_selected.connect(self._on_item_selected)
        left.addWidget(self.canvas, 1)

        btn_row = QHBoxLayout()
        self.add_btn = QPushButton("+ 添加按键")
        self.add_btn.setObjectName("Primary")
        self.add_btn.clicked.connect(self._add_button)
        btn_row.addWidget(self.add_btn)
        self.del_btn = QPushButton("删除按键")
        self.del_btn.clicked.connect(self._delete_button)
        btn_row.addWidget(self.del_btn)
        btn_row.addStretch(1)
        left.addLayout(btn_row)
        root.addLayout(left, 3)

        # 右列：属性面板
        right = QGroupBox("属性")
        right_l = QVBoxLayout(right)

        self.name_label = QLabel("未选择")
        self.name_label.setStyleSheet("font-size: 16px; color: #FFFFFF; font-weight: 600;")
        right_l.addWidget(self.name_label)

        label_row = QHBoxLayout()
        label_row.addWidget(QLabel("文字"))
        self.label_edit = QLineEdit()
        self.label_edit.setMaxLength(4)
        self.label_edit.setPlaceholderText("最多 4 个字符")
        self.label_edit.textChanged.connect(self._on_label_changed)
        label_row.addWidget(self.label_edit, 1)
        right_l.addLayout(label_row)

        xy_row = QHBoxLayout()
        xy_row.addWidget(QLabel("X"))
        self.x_spin = QSpinBox()
        self.x_spin.setRange(1, lw - 1)
        self.x_spin.valueChanged.connect(self._on_x_changed)
        xy_row.addWidget(self.x_spin)
        xy_row.addWidget(QLabel("Y"))
        self.y_spin = QSpinBox()
        self.y_spin.setRange((LITE_STATUS_H + 1) if self.lite else 1, lh - 1)
        self.y_spin.valueChanged.connect(self._on_y_changed)
        xy_row.addWidget(self.y_spin)
        right_l.addLayout(xy_row)

        shape_row = QHBoxLayout()
        shape_row.addWidget(QLabel("形状"))
        self.shape_combo = QComboBox()
        self.shape_combo.addItem("圆形", False)
        self.shape_combo.addItem("方形", True)
        self.shape_combo.currentIndexChanged.connect(self._on_shape_changed)
        shape_row.addWidget(self.shape_combo, 1)
        right_l.addLayout(shape_row)

        size_row = QHBoxLayout()
        self.size_label = QLabel("半径")
        size_row.addWidget(self.size_label)
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(4, 30)
        self.size_slider.valueChanged.connect(self._on_size_changed)
        size_row.addWidget(self.size_slider, 1)
        self.size_value = QLabel("")
        self.size_value.setMinimumWidth(50)
        size_row.addWidget(self.size_value)
        right_l.addLayout(size_row)

        # 摇杆专用
        self.lever_box = QGroupBox("街机摇杆")
        lever_l = QVBoxLayout(self.lever_box)
        lever_note = QLabel("摇杆捕获 D-Pad 方向；开启后自定义布局不显示移动键。")
        lever_note.setObjectName("Muted")
        lever_note.setWordWrap(True)
        lever_l.addWidget(lever_note)
        ring_row = QHBoxLayout()
        ring_row.addWidget(QLabel("环半径"))
        self.ring_slider = QSlider(Qt.Orientation.Horizontal)
        self.ring_slider.setRange(10, 40)
        self.ring_slider.valueChanged.connect(self._on_ring_changed)
        ring_row.addWidget(self.ring_slider, 1)
        self.ring_value = QLabel("")
        self.ring_value.setMinimumWidth(34)
        ring_row.addWidget(self.ring_value)
        lever_l.addLayout(ring_row)
        knob_row = QHBoxLayout()
        knob_row.addWidget(QLabel("摇杆半径"))
        self.knob_slider = QSlider(Qt.Orientation.Horizontal)
        self.knob_slider.setRange(2, 15)
        self.knob_slider.valueChanged.connect(self._on_knob_changed)
        knob_row.addWidget(self.knob_slider, 1)
        self.knob_value = QLabel("")
        self.knob_value.setMinimumWidth(34)
        knob_row.addWidget(self.knob_value)
        lever_l.addLayout(knob_row)
        right_l.addWidget(self.lever_box)

        right_l.addStretch(1)
        self.status_label = QLabel("")
        self.status_label.setObjectName("Muted")
        self.status_label.setWordWrap(True)
        right_l.addWidget(self.status_label)
        root.addWidget(right, 2)

    # ---------- 状态 ----------

    def _sync_from_state(self) -> None:
        # 载入时统一夹取：越界按键直接拉回屏内（旧状态文件/换屏都会踩到）
        w, h, sh = self._dims()
        fixed = sanitize_layout(self._layout(), w, h, status_h=sh)
        self.canvas.set_layout(self._layout())
        self._set_combo_by_data(self.default_combo, self.state.default_layout)
        self.lever_check.blockSignals(True)
        self.lever_check.setChecked(self._layout().show_lever)
        self.lever_check.blockSignals(False)
        self.canvas.set_selection(GROUP_MOVE, 0)
        self._sync_global_slider()
        self._refresh_panel()
        if fixed:
            # 内存修好了但固件头文件还是旧的：立刻按修好的布局重写一份
            self._write_and_save()
        elif self.lite:
            # Lite 的头文件完全由助手生成：若磁盘上和当前布局对不上（例如旧版本
            # 写进去的 240x135 越界坐标），打开页面就顺手补写一份正确的。
            out = self._lite_header_path()
            cur = ""
            if out is not None and out.exists():
                try:
                    cur = out.read_text(encoding="utf-8")
                except Exception:
                    cur = ""
            if out is not None and cur != generate_lite_layout_header(self._layout()):
                self._write_and_save()

    def _lite_header_path(self) -> Path | None:
        if not self.state.lite_source_dir:
            return None
        return Path(self.state.lite_source_dir) / "configs" / "GPFusionLite" / "layout_user.h"

    def reload_state(self) -> None:
        self._sync_from_state()

    def _layout(self) -> Layout:
        return self.state.lite_layout if self.lite else self.state.layout

    def _dims(self) -> tuple[int, int, int]:
        """返回 (宽, 高, 状态栏高度)，用于夹取/画布/滑条上限。"""
        if self.lite:
            return LITE_SCREEN[0], LITE_SCREEN[1], LITE_STATUS_H
        w, h = screen_dims(self.state.screen_res)
        return w, h, 0

    def _all_btns(self) -> list[Btn]:
        lay = self._layout()
        return list(lay.move) + list(lay.cluster)

    def _global_r_max(self) -> int:
        w, h, sh = self._dims()
        hard = max(3, min((w - 2) // 2, (h - 2) // 2, (h - 1 - sh) // 2))
        return max(3, min(40, hard))   # 40 与右侧「环半径」上限对齐，别把按键吹成巨无霸

    def _sync_global_slider(self) -> None:
        rs = [b.r for b in self._all_btns()]
        val = int(statistics.median(rs)) if rs else (6 if self.lite else 13)
        val = max(self.global_size.minimum(), min(self.global_size.maximum(), val))
        self.global_size.blockSignals(True)
        self.global_size.setValue(val)
        self.global_size.blockSignals(False)
        self._global_size_cur = val
        self.global_size_value.setText(str(val))

    @staticmethod
    def _set_combo_by_data(combo: QComboBox, value: int) -> None:
        combo.blockSignals(True)
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        combo.blockSignals(False)

    def _on_lever_toggled(self, checked: bool) -> None:
        self._layout().show_lever = checked
        self.canvas.update()
        if checked and self.canvas.sel_group == GROUP_MOVE:
            self.canvas.set_selection(GROUP_CLUSTER, 0)
        if not checked and self.canvas.sel_group == GROUP_LEVER:
            self.canvas.set_selection(GROUP_MOVE, 0)
        self._refresh_panel()
        self._write_and_save()

    def _on_default_changed(self) -> None:
        self.state.default_layout = int(self.default_combo.currentData())
        self.state.save()
        self._write_defaults()

    def _on_item_selected(self, group: str, index: int) -> None:
        self.canvas.set_selection(group, index)
        self._refresh_panel()

    def _group_items(self, group: str) -> list[Btn]:
        if group == GROUP_MOVE:
            return self._layout().move
        if group == GROUP_CLUSTER:
            return self._layout().cluster
        return []

    def _refresh_panel(self) -> None:
        group = self.canvas.sel_group
        index = self.canvas.sel_index
        if group == GROUP_LEVER:
            lv = self._layout().lever
            self.name_label.setText("街机摇杆")
            self.lever_box.setVisible(True)
            self.shape_combo.setEnabled(False)
            self.size_slider.setEnabled(False)
            self.label_edit.setEnabled(False)
            self.label_edit.blockSignals(True)
            self.label_edit.clear()
            self.label_edit.blockSignals(False)
            self.del_btn.setEnabled(True)   # 删除摇杆 = 隐藏
            self._set_spin(self.x_spin, lv.x)
            self._set_spin(self.y_spin, lv.y)
            self._set_slider(self.ring_slider, lv.ring)
            self.ring_value.setText(str(lv.ring))
            self._set_slider(self.knob_slider, lv.knob)
            self.knob_value.setText(str(lv.knob))
            return

        self.lever_box.setVisible(False)
        self.shape_combo.setEnabled(True)
        self.size_slider.setEnabled(True)
        self.label_edit.setEnabled(True)
        items = self._group_items(group)
        if not items:
            self.name_label.setText("（空）")
            self.del_btn.setEnabled(False)
            self.label_edit.setEnabled(False)
            return
        index = min(index, len(items) - 1)
        self.canvas.set_selection(group, index)
        b = items[index]
        self.name_label.setText(
            "%s（%s）" % (b.label, "方向键" if b.dpad else "功能键")
        )
        self.label_edit.blockSignals(True)
        self.label_edit.setText(b.label)
        self.label_edit.blockSignals(False)
        self.del_btn.setEnabled(True)
        self._set_spin(self.x_spin, b.x)
        self._set_spin(self.y_spin, b.y)
        self._set_combo(self.shape_combo, 1 if b.square else 0)
        self._set_slider(self.size_slider, b.r)
        self.size_label.setText("边长" if b.square else "半径")
        self.size_value.setText("%d" % (b.r * 2 if b.square else b.r))

    @staticmethod
    def _set_spin(spin: QSpinBox, value: int) -> None:
        spin.blockSignals(True)
        spin.setValue(max(spin.minimum(), min(spin.maximum(), value)))
        spin.blockSignals(False)

    @staticmethod
    def _set_slider(slider: QSlider, value: int) -> None:
        slider.blockSignals(True)
        slider.setValue(max(slider.minimum(), min(slider.maximum(), value)))
        slider.blockSignals(False)

    @staticmethod
    def _set_combo(combo: QComboBox, idx: int) -> None:
        combo.blockSignals(True)
        combo.setCurrentIndex(idx)
        combo.blockSignals(False)

    # ---------- 编辑回调 ----------

    def _selected_btn(self) -> Btn | None:
        group = self.canvas.sel_group
        if group == GROUP_LEVER:
            return None
        items = self._group_items(group)
        if not items or self.canvas.sel_index >= len(items):
            return None
        return items[self.canvas.sel_index]

    def _on_item_moved(self, group: str, index: int, x: int, y: int) -> None:
        items = self._group_items(group)
        if items and 0 <= index < len(items):
            items[index].x, items[index].y = x, y
        self._set_spin(self.x_spin, x)
        self._set_spin(self.y_spin, y)
        self._write_and_save()

    def _on_label_changed(self, text: str) -> None:
        b = self._selected_btn()
        if b is None:
            return
        cleaned = "".join(ch for ch in text.upper() if ch.isalnum() or ch in "-_")[:4]
        if cleaned != text:
            self.label_edit.blockSignals(True)
            self.label_edit.setText(cleaned)
            self.label_edit.blockSignals(False)
        if not cleaned:
            return
        b.label = cleaned
        self.name_label.setText(
            "%s（%s）" % (b.label, "方向键" if b.dpad else "功能键")
        )
        self.canvas.update()
        self._write_and_save()

    def _on_lever_moved(self, x: int, y: int) -> None:
        self._layout().lever.x, self._layout().lever.y = x, y
        self._set_spin(self.x_spin, x)
        self._set_spin(self.y_spin, y)
        self._write_and_save()

    def _on_x_changed(self, value: int) -> None:
        if self.canvas.sel_group == GROUP_LEVER:
            self._layout().lever.x = value
        else:
            b = self._selected_btn()
            if b:
                b.x = value
        self.canvas.update()
        self._write_and_save()

    def _on_y_changed(self, value: int) -> None:
        if self.canvas.sel_group == GROUP_LEVER:
            self._layout().lever.y = value
        else:
            b = self._selected_btn()
            if b:
                b.y = value
        self.canvas.update()
        self._write_and_save()

    def _on_shape_changed(self, index: int) -> None:
        b = self._selected_btn()
        if b:
            b.square = bool(self.shape_combo.itemData(index))
            self.size_label.setText("边长" if b.square else "半径")
            self.size_value.setText("%d" % (b.r * 2 if b.square else b.r))
            self.canvas.update()
            self._write_and_save()

    def _on_size_changed(self, value: int) -> None:
        b = self._selected_btn()
        if b:
            b.r = value
            self.size_value.setText("%d" % (b.r * 2 if b.square else b.r))
            self.canvas.update()
            self._write_and_save()

    def _on_ring_changed(self, value: int) -> None:
        self._layout().lever.ring = value
        self.ring_value.setText(str(value))
        self.canvas.update()
        self._write_and_save()

    def _on_knob_changed(self, value: int) -> None:
        self._layout().lever.knob = value
        self.knob_value.setText(str(value))
        self.canvas.update()
        self._write_and_save()

    def _on_global_size_preview(self, value: int) -> None:
        delta = value - getattr(self, "_global_size_cur", value)
        self._global_size_cur = value
        self.global_size_value.setText(str(value))
        if delta:
            r_max = self._global_r_max()
            for b in self._all_btns():
                b.r = max(3, min(r_max, b.r + delta))
            if self.lever_scale_check.isChecked() and self._layout().show_lever:
                lv = self._layout().lever
                lv.ring = max(3, min(r_max, lv.ring + delta))
                lv.knob = max(1, min(lv.ring - 1, lv.knob + delta))
        w, h, sh = self._dims()
        sanitize_layout(self._layout(), w, h, status_h=sh)
        self.canvas.update()
        self._refresh_panel()

    def _on_global_size_committed(self) -> None:
        self._write_and_save()

    # ---------- 增删按键 ----------

    def _add_button(self) -> None:
        dlg = AddButtonDialog(self)
        if dlg.exec() != AddButtonDialog.DialogCode.Accepted:
            return
        chosen = dlg.chosen()
        if not chosen:
            return
        label, mask = chosen
        x, y = find_free_spot(self._layout(), self.canvas._lw, self.canvas._lh)
        self._layout().cluster.append(
            Btn(mask, x, y, 6 if self.lite else 13, False, label, False)
        )
        self.canvas.set_selection(
            GROUP_CLUSTER, len(self._layout().cluster) - 1
        )
        self.canvas.update()
        self._sync_global_slider()
        self._refresh_panel()
        self._write_and_save()

    def _delete_button(self) -> None:
        group = self.canvas.sel_group
        if group == GROUP_LEVER:
            # 删除摇杆 = 隐藏，之后可通过「显示街机摇杆」重新打开
            self._layout().show_lever = False
            self.lever_check.blockSignals(True)
            self.lever_check.setChecked(False)
            self.lever_check.blockSignals(False)
            self.canvas.set_selection(GROUP_MOVE, 0)
            self.canvas.update()
            self._refresh_panel()
            self._write_and_save()
            self.status_label.setText("已隐藏街机摇杆")
            self.status_label.setStyleSheet("color: #FFB454;")
            return
        items = self._group_items(group)
        if not items or self.canvas.sel_index >= len(items):
            return
        removed = items.pop(self.canvas.sel_index)
        if items:
            self.canvas.sel_index = min(self.canvas.sel_index, len(items) - 1)
        else:
            self.canvas.sel_index = 0
        self.canvas.update()
        self._sync_global_slider()
        self._refresh_panel()
        self._write_and_save()
        self.status_label.setText("已删除 %s" % removed.label)
        self.status_label.setStyleSheet("color: #FFB454;")

    # ---------- 写入 ----------

    def reset_defaults(self) -> None:
        if self.lite:
            self.state.lite_layout = Layout.lite_preset()
        elif self.state.screen_res == "170x320":
            self.state.layout = Layout.preset_170x320()
        else:
            self.state.layout = Layout.preset()
        self.canvas.set_layout(self._layout())
        self.lever_check.blockSignals(True)
        self.lever_check.setChecked(False)
        self.lever_check.blockSignals(False)
        self.canvas.set_selection(GROUP_MOVE, 0)
        self._sync_global_slider()
        self._refresh_panel()
        self.canvas.update()
        self._write_and_save()

    def _write_and_save(self) -> None:
        # 写头文件前再夹一次：拖到边缘/放大后越界的按键会被拉回屏内
        w, h, sh = self._dims()
        fixed = sanitize_layout(self._layout(), w, h, status_h=sh)
        self.state.save()
        src = self.state.lite_source_dir if self.lite else self.state.source_dir
        if not src:
            self.status_label.setText("源码目录未就绪，布局改动未写入固件")
            self.status_label.setStyleSheet("color: #FFB454;")
            return
        try:
            if self.lite:
                out = self._lite_header_path()
                write_lite_layout_header(self._layout(), out)
            else:
                out = local_layout_header(Path(src), self.state.screen_res)
                write_layout_header(self._layout(), out)
            note = "（已修正 %d 个越界按键）" % fixed if fixed else ""
            self.status_label.setText("✔ 已实时写入 %s%s" % (out, note))
            self.status_label.setStyleSheet("color: #64E0A0;")
            self.changed.emit()
        except Exception as exc:  # noqa: BLE001
            self.status_label.setText("写入失败：%s" % exc)
            self.status_label.setStyleSheet("color: #FF7B72;")

    def _write_defaults(self) -> None:
        if self.lite:
            return  # Lite 不生成 defaults.h
        if not self.state.source_dir:
            self.status_label.setText("源码目录未就绪，默认布局未写入固件")
            self.status_label.setStyleSheet("color: #FFB454;")
            return
        try:
            out = local_defaults_header(Path(self.state.source_dir))
            write_defaults_header(self.state.default_layout, out)
            self.status_label.setText("✔ 默认布局已写入 %s" % out)
            self.status_label.setStyleSheet("color: #64E0A0;")
            self.changed.emit()
        except Exception as exc:  # noqa: BLE001
            self.status_label.setText("写入失败：%s" % exc)
            self.status_label.setStyleSheet("color: #FF7B72;")
