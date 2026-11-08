"""小游戏（NES）配置：缩放模式 + ROM 导入（仅 170x320 版）。"""
from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..app_config import local_nes_conf, local_nes_dir
from ..wizard_state import WizardState

SCALE_MODES = [("1", "等比居中（左右黑边，推荐）"), ("0", "拉伸铺满（画面变形）")]


class NesPage(QWidget):
    changed = Signal()

    def __init__(self, state: WizardState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._build_ui()
        self.reload_state()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 12)
        title = QLabel("小游戏（NES）")
        title.setObjectName("StepTitle")
        root.addWidget(title)
        self.hint = QLabel(
            "仅 170x320 版支持。ROM 会被写入设备卡内 /nes/，"
            "在机内滑动菜单「小游戏」里选择运行。"
        )
        self.hint.setObjectName("Hint")
        self.hint.setWordWrap(True)
        root.addWidget(self.hint)
        root.addSpacing(8)

        opt = QGroupBox("画面")
        opt_l = QHBoxLayout(opt)
        opt_l.addWidget(QLabel("缩放模式"))
        self.scale_combo = QComboBox()
        for val, name in SCALE_MODES:
            self.scale_combo.addItem(name, val)
        self.scale_combo.currentIndexChanged.connect(self._on_scale_changed)
        opt_l.addWidget(self.scale_combo, 1)
        root.addWidget(opt)

        rom = QGroupBox("ROM 导入")
        rom_l = QVBoxLayout(rom)
        btn_row = QHBoxLayout()
        add_btn = QPushButton("导入 ROM（.nes）…")
        add_btn.clicked.connect(self.import_roms)
        btn_row.addWidget(add_btn)
        del_btn = QPushButton("删除选中")
        del_btn.clicked.connect(self.remove_selected)
        btn_row.addWidget(del_btn)
        btn_row.addStretch(1)
        rom_l.addLayout(btn_row)
        self.rom_list = QListWidget()
        self.rom_list.setFixedHeight(200)
        rom_l.addWidget(self.rom_list)
        self.rom_status = QLabel("")
        self.rom_status.setObjectName("Muted")
        self.rom_status.setWordWrap(True)
        rom_l.addWidget(self.rom_status)
        root.addWidget(rom)
        root.addStretch(1)

    # ---------- 状态 ----------

    def reload_state(self) -> None:
        enabled = self.state.screen_res == "170x320"
        self.scale_combo.setEnabled(enabled)
        self.rom_list.setEnabled(enabled)
        if not enabled:
            self.hint.setStyleSheet("color: #FFB454;")
            self.hint.setText(
                "小游戏功能仅支持 170x320 版（在「设备与源码」页切换分辨率后启用）"
            )
            self.scale_combo.setCurrentIndex(0)
            self._refresh_rom_list()
            return
        self.hint.setStyleSheet("")
        self.hint.setText(
            "ROM 会被写入设备卡内 /nes/，在机内滑动菜单「小游戏」里选择运行。"
        )
        conf = local_nes_conf(Path(self.state.source_dir), self.state.screen_res) \
            if self.state.source_dir else None
        val = "1"
        if conf and conf.is_file():
            txt = conf.read_text(encoding="utf-8")
            if "NES_SCALE_MODE 0" in txt:
                val = "0"
        idx = self.scale_combo.findData(val)
        if idx >= 0:
            self.scale_combo.blockSignals(True)
            self.scale_combo.setCurrentIndex(idx)
            self.scale_combo.blockSignals(False)
        self._refresh_rom_list()

    def _refresh_rom_list(self) -> None:
        self.rom_list.clear()
        if not self.state.source_dir:
            self.rom_status.setText("源码目录未就绪")
            return
        d = local_nes_dir(Path(self.state.source_dir))
        files = sorted(d.glob("*.nes")) if d.is_dir() else []
        for f in files:
            self.rom_list.addItem("%s  (%.0f KB)" % (f.name, f.stat().st_size / 1024))
        self.rom_status.setText(
            "已导入 %d 个 ROM（写入设备后需重刷一次固件设置）" % len(files)
        )

    # ---------- 操作 ----------

    def _on_scale_changed(self) -> None:
        if not self.state.source_dir or self.state.screen_res != "170x320":
            return
        val = str(self.scale_combo.currentData())
        conf = local_nes_conf(Path(self.state.source_dir), self.state.screen_res)
        try:
            conf.write_text(
                "#pragma once\n// 由 GP-Combine 配置助手生成：NES 缩放模式\n"
                "#define NES_SCALE_MODE %s\n" % val,
                encoding="utf-8",
            )
            self.rom_status.setText("✔ 已写入 %s（缩放模式）" % conf.name)
        except Exception as exc:  # noqa: BLE001
            self.rom_status.setText("写入失败：%s" % exc)

    def import_roms(self) -> None:
        if self.state.screen_res != "170x320":
            self.rom_status.setText("小游戏仅支持 170x320 版")
            return
        if not self.state.source_dir:
            self.rom_status.setText("源码目录未就绪")
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择 NES ROM", str(Path.home()), "NES ROM (*.nes)"
        )
        if not paths:
            return
        d = local_nes_dir(Path(self.state.source_dir))
        d.mkdir(parents=True, exist_ok=True)
        ok = 0
        for p in paths:
            src = Path(p)
            dst = d / src.name
            try:
                shutil.copy2(src, dst)
                ok += 1
            except Exception:  # noqa: BLE001
                pass
        self._refresh_rom_list()
        self.rom_status.setText("✔ 导入 %d 个 ROM 到 %s" % (ok, d))
        self.changed.emit()

    def remove_selected(self) -> None:
        item = self.rom_list.currentItem()
        if item is None:
            return
        name = item.text().split("  (", 1)[0]
        f = local_nes_dir(Path(self.state.source_dir)) / name
        if f.is_file():
            f.unlink()
        self._refresh_rom_list()
        self.changed.emit()
