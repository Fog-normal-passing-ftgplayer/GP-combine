"""步骤：正式版 Pico 配置（WS2812B 灯带引脚/每键灯数）。

热键与灯序均已移至网页配置步骤（192.168.7.1），不再由本页生成。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..app_config import local_pico_user_header
from ..pico_config import write_pico_user_header
from ..wizard_state import WizardState


class PicoConfigPage(QWidget):
    changed = Signal()

    def __init__(self, state: WizardState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._build_ui()
        self._sync_from_state()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 12)
        title = QLabel("第 5 步：Pico 配置（正式版）")
        title.setObjectName("StepTitle")
        root.addWidget(title)
        hint = QLabel("配置正式版 Pico 的 WS2812B 灯带。"
                      "这里只设置数据引脚与每键灯数，改动实时写入 pico_user.h。"
                      "热键与按键→LED 灯序请在「网页配置」步骤连接 192.168.7.1 设置。")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        # 可上下滚动的配置区
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll_body = QWidget()
        scroll_l = QVBoxLayout(scroll_body)
        scroll_l.setContentsMargins(0, 0, 8, 0)

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
        scroll_l.addWidget(led)
        scroll_l.addStretch(1)
        scroll.setWidget(scroll_body)
        root.addWidget(scroll, 1)

        self.status_label = QLabel("")
        self.status_label.setObjectName("Muted")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

    def _sync_from_state(self) -> None:
        self.led_pin.blockSignals(True)
        self.led_pin.setValue(self.state.led_pin)
        self.led_pin.blockSignals(False)
        self.leds_per.blockSignals(True)
        self.leds_per.setValue(self.state.leds_per_button)
        self.leds_per.blockSignals(False)

    def reload_state(self) -> None:
        self._sync_from_state()

    def _collect(self) -> None:
        self.state.led_pin = self.led_pin.value()
        self.state.leds_per_button = self.leds_per.value()
        self.state.save()
        self._write()

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
                led_pin=self.state.led_pin,
                leds_per_button=self.state.leds_per_button,
            )
            msg = "✔ 已写入 %s" % out
            self.status_label.setText(msg)
            self.status_label.setStyleSheet("color: #64E0A0;")
            self.changed.emit()
        except Exception as exc:  # noqa: BLE001
            self.status_label.setText("写入失败：%s" % exc)
            self.status_label.setStyleSheet("color: #FF7B72;")
