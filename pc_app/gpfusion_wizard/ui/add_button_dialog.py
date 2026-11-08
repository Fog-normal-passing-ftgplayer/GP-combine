"""添加额外按键的对话框（L3/R3/S1/S2/A1/A2/A3/A4）。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ..layout_model import EXTRA_BUTTONS


class AddButtonDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("添加按键")
        self.setModal(True)
        self.setMinimumWidth(360)

        root = QVBoxLayout(self)
        hint = QLabel("选择要额外映射到屏幕上的按键，添加后可拖动位置、调整大小。")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        row = QHBoxLayout()
        row.addWidget(QLabel("按键"))
        self.combo = QComboBox()
        for label, mask in EXTRA_BUTTONS:
            self.combo.addItem("%s  (0x%04X)" % (label, mask), (label, mask))
        row.addWidget(self.combo, 1)
        root.addLayout(row)

        note = QLabel("这些按键跟随 UART 全 16 位数据传递，按下时会点亮屏幕上的对应按键。")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        root.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def chosen(self) -> tuple[str, int] | None:
        data = self.combo.currentData()
        return data if isinstance(data, tuple) else None
