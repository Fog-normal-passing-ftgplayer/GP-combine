"""步骤：正式版 Pico 配置（热键单键引脚映射 + WS2812B 灯键顺序/每键灯数）。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..app_config import local_pico_user_header
from ..pico_config import BUTTONS, DEFAULT_LED_ORDER, HOTKEY_ACTIONS, write_pico_user_header
from ..wizard_state import WizardState


class PicoConfigPage(QWidget):
    changed = Signal()

    def __init__(self, state: WizardState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._hotkey_combos: list[tuple[QComboBox, QComboBox]] = []
        self._led_spins: list[tuple[str, QSpinBox]] = []
        self._build_ui()
        self._sync_from_state()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 12)
        title = QLabel("步骤：Pico 配置（正式版）")
        title.setObjectName("StepTitle")
        root.addWidget(title)
        hint = QLabel("配置正式版 Pico 的热键单键引脚映射与 WS2812B 灯带"
                      "（按键顺序 / 每键灯数），改动实时写入 pico_user.h。")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        # 热键
        hot = QGroupBox("热键（单键触发）")
        hot_l = QVBoxLayout(hot)
        grid = QGridLayout()
        grid.addWidget(QLabel("槽位"), 0, 0)
        grid.addWidget(QLabel("动作"), 0, 1)
        grid.addWidget(QLabel("触发按键"), 0, 2)
        for i in range(16):
            slot = QLabel("热键 %02d" % (i + 1))
            grid.addWidget(slot, i + 1, 0)
            act = QComboBox()
            for name, val in HOTKEY_ACTIONS:
                act.addItem(name, val)
            act.addItem("（禁用）", 0)
            act.setCurrentIndex(act.count() - 1)
            btn = QComboBox()
            for label, _m, _p in BUTTONS:
                btn.addItem(label, label)
            btn.setCurrentIndex(btn.findData("S2"))
            act.currentIndexChanged.connect(self._on_hotkey_changed)
            btn.currentIndexChanged.connect(self._on_hotkey_changed)
            grid.addWidget(act, i + 1, 1)
            grid.addWidget(btn, i + 1, 2)
            self._hotkey_combos.append((act, btn))
        hot_l.addLayout(grid)
        root.addWidget(hot)

        # LED
        led = QGroupBox("WS2812B 灯带")
        led_l = QVBoxLayout(led)
        row = QHBoxLayout()
        row.addWidget(QLabel("数据引脚"))
        self.led_pin = QSpinBox()
        self.led_pin.setRange(0, 28)
        self.led_pin.valueChanged.connect(self._on_led_changed)
        row.addWidget(self.led_pin)
        row.addWidget(QLabel("每键灯数"))
        self.leds_per = QSpinBox()
        self.leds_per.setRange(1, 8)
        self.leds_per.valueChanged.connect(self._on_led_changed)
        row.addWidget(self.leds_per)
        row.addStretch(1)
        led_l.addLayout(row)
        grid2 = QGridLayout()
        grid2.addWidget(QLabel("按键"), 0, 0)
        grid2.addWidget(QLabel("LED 索引"), 0, 1)
        grid2.addWidget(QLabel("按键"), 0, 2)
        grid2.addWidget(QLabel("LED 索引"), 0, 3)
        for i, (name, _idx) in enumerate(DEFAULT_LED_ORDER):
            col = 0 if i % 2 == 0 else 2
            row_ = (i // 2) + 1
            grid2.addWidget(QLabel(name), row_, col)
            sp = QSpinBox()
            sp.setRange(0, 63)
            sp.valueChanged.connect(self._on_led_changed)
            grid2.addWidget(sp, row_, col + 1)
            self._led_spins.append((name, sp))
        led_l.addLayout(grid2)
        root.addWidget(led)

        self.status_label = QLabel("")
        self.status_label.setObjectName("Muted")
        root.addWidget(self.status_label)
        root.addStretch(1)

    def _sync_from_state(self) -> None:
        self.led_pin.blockSignals(True)
        self.led_pin.setValue(self.state.led_pin)
        self.led_pin.blockSignals(False)
        self.leds_per.blockSignals(True)
        self.leds_per.setValue(self.state.leds_per_button)
        self.leds_per.blockSignals(False)
        for i, (act, btn) in enumerate(self._hotkey_combos):
            entry = self.state.hotkeys[i] if i < len(self.state.hotkeys) else {}
            act.blockSignals(True)
            idx = act.findData(int(entry.get("action", 0)))
            act.setCurrentIndex(idx if idx >= 0 else act.count() - 1)
            act.blockSignals(False)
            btn.blockSignals(True)
            b = str(entry.get("button", "S2"))
            bi = btn.findData(b)
            btn.setCurrentIndex(bi if bi >= 0 else 0)
            btn.blockSignals(False)
        for name, sp in self._led_spins:
            sp.blockSignals(True)
            sp.setValue(int(self.state.led_order.get(name, dict(DEFAULT_LED_ORDER)[name])))
            sp.blockSignals(False)

    def _collect(self) -> None:
        self.state.hotkeys = []
        for act, btn in self._hotkey_combos:
            self.state.hotkeys.append({
                "action": int(act.currentData()),
                "button": str(btn.currentData()),
            })
        self.state.led_pin = self.led_pin.value()
        self.state.leds_per_button = self.leds_per.value()
        self.state.led_order = {name: sp.value() for name, sp in self._led_spins}
        self.state.save()
        self._write()

    def _on_hotkey_changed(self) -> None:
        self._collect()

    def _on_led_changed(self) -> None:
        self._collect()

    def _write(self) -> None:
        if not self.state.source_dir:
            self.status_label.setText("源码目录未就绪，Pico 配置未写入")
            self.status_label.setStyleSheet("color: #FFB454;")
            return
        try:
            out = local_pico_user_header(Path(self.state.source_dir))
            write_pico_user_header(
                out,
                hotkeys=self.state.hotkeys,
                led_pin=self.state.led_pin,
                leds_per_button=self.state.leds_per_button,
                led_order=self.state.led_order,
            )
            self.status_label.setText("✔ 已写入 %s" % out)
            self.status_label.setStyleSheet("color: #64E0A0;")
            self.changed.emit()
        except Exception as exc:  # noqa: BLE001
            self.status_label.setText("写入失败：%s" % exc)
            self.status_label.setStyleSheet("color: #FF7B72;")
