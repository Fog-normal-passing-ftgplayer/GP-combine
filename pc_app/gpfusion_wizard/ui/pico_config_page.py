"""步骤：正式版 Pico 配置（WS2812B 灯键顺序/每键灯数）。

热键配置已移至网页配置步骤（192.168.7.1），不再由本页生成。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..app_config import local_pico_user_header
from ..pico_config import DEFAULT_LED_ORDER, write_pico_user_header
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
                      "灯带按「排序模式」排列：列表里从上到下就是 LED 索引 0、1、2…，"
                      "可拖拽或点上下按钮调整，改动实时写入 pico_user.h。"
                      "热键与按键映射请在「网页配置」步骤连接 192.168.7.1 设置。")
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
        order_row = QHBoxLayout()
        order_hint = QLabel("按键 → LED 顺序（列表位置即索引）")
        order_hint.setObjectName("Muted")
        order_row.addWidget(order_hint)
        order_row.addStretch(1)
        up_btn = QPushButton("上移")
        up_btn.clicked.connect(lambda: self._move_led(-1))
        order_row.addWidget(up_btn)
        down_btn = QPushButton("下移")
        down_btn.clicked.connect(lambda: self._move_led(1))
        order_row.addWidget(down_btn)
        reset_btn = QPushButton("恢复默认顺序")
        reset_btn.clicked.connect(self._reset_led_order)
        order_row.addWidget(reset_btn)
        led_l.addLayout(order_row)

        self.led_list = QListWidget()
        self.led_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.led_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.led_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.led_list.setFixedHeight(210)
        self.led_list.model().rowsMoved.connect(self._on_led_reordered)
        led_l.addWidget(self.led_list)
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
        self._rebuild_led_list()

    def reload_state(self) -> None:
        self._sync_from_state()

    def _rebuild_led_list(self) -> None:
        self.led_list.blockSignals(True)
        self.led_list.clear()
        default_idx = dict(DEFAULT_LED_ORDER)
        names = sorted(
            (name for name, _ in DEFAULT_LED_ORDER),
            key=lambda n: int(self.state.led_order.get(n, default_idx[n])),
        )
        for i, name in enumerate(names):
            item = QListWidgetItem("%02d  %s" % (i, name))
            self.led_list.addItem(item)
        self.led_list.blockSignals(False)

    def _move_led(self, delta: int) -> None:
        row = self.led_list.currentRow()
        target = row + delta
        if row < 0 or target < 0 or target >= self.led_list.count():
            return
        item = self.led_list.takeItem(row)
        self.led_list.insertItem(target, item)
        self.led_list.setCurrentRow(target)
        self._on_led_reordered()

    def _reset_led_order(self) -> None:
        self.state.led_order = {name: idx for name, idx in DEFAULT_LED_ORDER}
        self._rebuild_led_list()
        self._on_led_reordered()

    def _led_order_from_list(self) -> dict[str, int]:
        order: dict[str, int] = {}
        for i in range(self.led_list.count()):
            text = self.led_list.item(i).text()
            order[text.split("  ", 1)[1]] = i
        return order

    def _collect(self) -> None:
        self.state.led_pin = self.led_pin.value()
        self.state.leds_per_button = self.leds_per.value()
        self.state.led_order = self._led_order_from_list()
        self.state.save()
        self._write()

    def _on_led_changed(self) -> None:
        self._collect()

    def _on_led_reordered(self) -> None:
        self._refresh_led_list_text()
        self._collect()

    def _refresh_led_list_text(self) -> None:
        for i in range(self.led_list.count()):
            item = self.led_list.item(i)
            name = item.text().split("  ", 1)[1]
            item.setText("%02d  %s" % (i, name))

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
                led_order=self.state.led_order,
            )
            msg = "✔ 已写入 %s" % out
            self.status_label.setText(msg)
            self.status_label.setStyleSheet("color: #64E0A0;")
            self.changed.emit()
        except Exception as exc:  # noqa: BLE001
            self.status_label.setText("写入失败：%s" % exc)
            self.status_label.setStyleSheet("color: #FF7B72;")
