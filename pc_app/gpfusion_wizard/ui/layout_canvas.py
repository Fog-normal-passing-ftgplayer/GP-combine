"""240x135 逻辑画布：渲染并交互编辑「自定义」布局。

画布始终显示统一的用户自定义布局：4 个移动键 + 右侧按键组
（可增删）+ 可选街机摇杆，所有可见元素都可以直接拖动/选中。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..app_config import SCREEN_H, SCREEN_W
from ..layout_model import GROUP_CLUSTER, GROUP_LEVER, GROUP_MOVE, Btn, Layout

COL_RING = QColor(150, 160, 175)
COL_KNOB = QColor(80, 200, 255)
COL_BG = QColor(21, 27, 39)


class LayoutCanvas(QWidget):
    item_moved = Signal(str, int, int, int)      # group, index, x, y
    lever_moved = Signal(int, int)               # x, y
    item_selected = Signal(str, int)             # group, index

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(SCREEN_W * 2, SCREEN_H * 2)
        self.layout_data: Layout = Layout.preset()
        self.sel_group: str = GROUP_MOVE
        self.sel_index: int = 0
        self._drag: tuple[str, int] | None = None
        self.setMouseTracking(True)

    # ---------- 对外设置 ----------

    def set_layout(self, layout: Layout) -> None:
        self.layout_data = layout
        self.update()

    def set_selection(self, group: str, index: int) -> None:
        self.sel_group = group
        self.sel_index = index
        self.update()

    # ---------- 数据 ----------

    def _all_buttons(self) -> list[tuple[str, int, Btn]]:
        """可见按键：摇杆开启时移动键隐藏（摇杆捕获 D-Pad，与街机预设一致）。"""
        out: list[tuple[str, int, Btn]] = []
        if not self.layout_data.show_lever:
            out += [(GROUP_MOVE, i, b) for i, b in enumerate(self.layout_data.move)]
        out += [(GROUP_CLUSTER, i, b) for i, b in enumerate(self.layout_data.cluster)]
        return out

    def _group_items(self, group: str) -> list[Btn]:
        if group == GROUP_MOVE:
            return self.layout_data.move
        if group == GROUP_CLUSTER:
            return self.layout_data.cluster
        return []

    def _show_lever(self) -> bool:
        return self.layout_data.show_lever

    def _scale(self) -> float:
        return min(self.width() / SCREEN_W, self.height() / SCREEN_H)

    def _origin(self) -> tuple[int, int]:
        s = self._scale()
        return (
            int((self.width() - SCREEN_W * s) / 2),
            int((self.height() - SCREEN_H * s) / 2),
        )

    def _to_logic(self, pos) -> tuple[int, int]:
        s = self._scale()
        ox, oy = self._origin()
        return int((pos.x() - ox) / s), int((pos.y() - oy) / s)

    # ---------- 交互 ----------

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        x, y = self._to_logic(event.position())
        if self._show_lever():
            lv = self.layout_data.lever
            if (x - lv.x) ** 2 + (y - lv.y) ** 2 <= (lv.ring + 6) ** 2:
                self.sel_group, self.sel_index = GROUP_LEVER, 0
                self._drag = (GROUP_LEVER, 0)
                self.item_selected.emit(GROUP_LEVER, 0)
                self.update()
                return
        for group, idx, b in reversed(self._all_buttons()):
            hit_r = max(8, b.r + 6)
            if (x - b.x) ** 2 + (y - b.y) ** 2 <= hit_r ** 2:
                self.sel_group, self.sel_index = group, idx
                self._drag = (group, idx)
                self.item_selected.emit(group, idx)
                self.update()
                return

    def mouseMoveEvent(self, event) -> None:
        if self._drag is None:
            return
        x, y = self._to_logic(event.position())
        group, idx = self._drag
        if group == GROUP_LEVER:
            lv = self.layout_data.lever
            margin = 2
            x = max(lv.ring + margin, min(SCREEN_W - 1 - lv.ring - margin, x))
            y = max(lv.ring + margin, min(SCREEN_H - 1 - lv.ring - margin, y))
            lv.x, lv.y = x, y
            self.lever_moved.emit(x, y)
            self.update()
            return
        items = self._group_items(group)
        if idx >= len(items):
            return
        b = items[idx]
        x = max(b.r + 1, min(SCREEN_W - 1 - b.r, x))
        y = max(b.r + 1, min(SCREEN_H - 1 - b.r, y))
        b.x, b.y = x, y
        self.item_moved.emit(group, idx, x, y)
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        self._drag = None

    def leaveEvent(self, event) -> None:
        self._drag = None

    # ---------- 渲染 ----------

    def paintEvent(self, event) -> None:
        s = self._scale()
        ox, oy = self._origin()
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(10, 14, 20))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        content = QRectF(ox, oy, SCREEN_W * s, SCREEN_H * s)
        painter.fillRect(content, COL_BG)
        painter.setPen(QPen(QColor(49, 65, 91), 1))
        painter.drawRect(content)

        painter.save()
        painter.translate(ox, oy)
        painter.scale(s, s)

        if self._show_lever():
            self._draw_lever(painter)
        for group, idx, b in self._all_buttons():
            self._draw_btn(painter, b)
            if group == self.sel_group and idx == self.sel_index:
                self._draw_highlight(painter, b)
        if self.sel_group == GROUP_LEVER and self.sel_index == 0:
            lv = self.layout_data.lever
            painter.setPen(QPen(QColor(255, 255, 255), 1, Qt.PenStyle.DashLine))
            painter.drawEllipse(lv.x - lv.ring - 2, lv.y - lv.ring - 2,
                                (lv.ring + 2) * 2, (lv.ring + 2) * 2)
        painter.restore()

    def _draw_highlight(self, painter: QPainter, b: Btn) -> None:
        painter.setPen(QPen(QColor(255, 255, 255), 1, Qt.PenStyle.DashLine))
        painter.drawEllipse(b.x - b.r - 3, b.y - b.r - 3, (b.r + 3) * 2, (b.r + 3) * 2)

    def _draw_btn(self, painter: QPainter, b: Btn) -> None:
        font = QFont("sans-serif", max(5, b.r - 2))
        painter.setFont(font)
        if b.square:
            size = b.r * 2
            x0, y0 = b.x - b.r, b.y - b.r
            painter.setPen(QPen(COL_RING, 1))
            painter.drawRect(x0, y0, size, size)
            painter.drawText(x0, y0, size, size,
                             Qt.AlignmentFlag.AlignCenter, b.label)
        else:
            painter.setPen(QPen(COL_RING, 1))
            painter.drawEllipse(b.x - b.r, b.y - b.r, b.r * 2, b.r * 2)
            painter.drawText(b.x - b.r, b.y - b.r, b.r * 2, b.r * 2,
                             Qt.AlignmentFlag.AlignCenter, b.label)

    def _draw_lever(self, painter: QPainter) -> None:
        lv = self.layout_data.lever
        painter.setPen(QPen(COL_RING, 1))
        painter.drawEllipse(lv.x - lv.ring, lv.y - lv.ring,
                            lv.ring * 2, lv.ring * 2)
        painter.setBrush(COL_KNOB)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(lv.x - lv.knob, lv.y - lv.knob,
                            lv.knob * 2, lv.knob * 2)
