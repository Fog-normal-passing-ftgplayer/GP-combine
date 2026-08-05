"""向导主窗口：左侧步骤栏 + 右侧内容页。"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..app_config import APP_NAME, APP_VERSION
from ..wizard_state import WizardState
from .background_page import BackgroundPage
from .layout_page import LayoutPage
from .prep_page import PrepPage
from .upload_page import UploadPage

STEPS = [
    "连接与准备",
    "背景图",
    "按键布局",
    "编译上传",
]


class MainWindow(QWidget):
    closed = Signal()

    def __init__(self, state: WizardState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self.setWindowTitle("%s v%s" % (APP_NAME, APP_VERSION))
        self.resize(1100, 720)
        self.setObjectName("Root")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        body = QWidget()
        root = QHBoxLayout(body)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 左侧步骤栏
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(210)
        side_l = QVBoxLayout(sidebar)
        side_l.setContentsMargins(12, 22, 12, 16)
        app_title = QLabel("GP-Fusion")
        app_title.setObjectName("AppTitle")
        app_sub = QLabel("配置向导 · 平民固件")
        app_sub.setObjectName("AppSub")
        side_l.addWidget(app_title)
        side_l.addWidget(app_sub)
        side_l.addSpacing(22)

        self.step_list = QListWidget()
        self.step_list.setObjectName("Steps")
        for name in STEPS:
            item = QListWidgetItem(name)
            self.step_list.addItem(item)
        side_l.addWidget(self.step_list)
        side_l.addStretch(1)
        ver = QLabel("v%s" % APP_VERSION)
        ver.setObjectName("AppSub")
        side_l.addWidget(ver)
        root.addWidget(sidebar)

        # 右侧内容区
        self.stack = QStackedWidget()
        self.prep_page = PrepPage(self.state)
        self.bg_page = BackgroundPage(self.state)
        self.layout_page = LayoutPage(self.state)
        self.upload_page = UploadPage(self.state)
        self.stack.addWidget(self.prep_page)
        self.stack.addWidget(self.bg_page)
        self.stack.addWidget(self.layout_page)
        self.stack.addWidget(self.upload_page)
        root.addWidget(self.stack, 1)
        outer.addWidget(body, 1)

        # 底部导航（叠加在内容区右侧的独立栏）
        self.nav_bar = QWidget()
        nav_l = QHBoxLayout(self.nav_bar)
        nav_l.setContentsMargins(28, 10, 28, 14)
        self.back_btn = QPushButton("上一步")
        self.back_btn.clicked.connect(self._go_back)
        nav_l.addWidget(self.back_btn)
        nav_l.addStretch(1)
        self.next_btn = QPushButton("下一步")
        self.next_btn.setObjectName("Primary")
        self.next_btn.clicked.connect(self._go_next)
        nav_l.addWidget(self.next_btn)
        self.finish_btn = QPushButton("完成")
        self.finish_btn.setObjectName("Primary")
        self.finish_btn.clicked.connect(self.close)
        self.finish_btn.setVisible(False)
        nav_l.addWidget(self.finish_btn)

        outer.addWidget(self.nav_bar)

        self.prep_page.ready_changed.connect(self._update_nav)
        self.upload_page.finished_upload.connect(self._on_upload_finished)
        self.step_list.currentRowChanged.connect(self._go_to)
        self.step_list.setCurrentRow(0)
        self._update_nav()

    # ---------- 导航 ----------

    def _go_to(self, row: int) -> None:
        row = max(0, min(row, self.stack.count() - 1))
        cur = self.stack.currentIndex()
        if cur >= 0 and row > cur and not self._can_continue(cur):
            return
        self.stack.setCurrentIndex(row)
        if row == 3:
            self.upload_page.on_shown()
        self._update_nav()

    def _go_back(self) -> None:
        self._go_to(self.stack.currentIndex() - 1)

    def _go_next(self) -> None:
        self._go_to(self.stack.currentIndex() + 1)

    def _update_nav(self) -> None:
        idx = self.stack.currentIndex()
        self.back_btn.setEnabled(idx > 0)
        last = idx == 3
        self.next_btn.setVisible(not last)
        self.finish_btn.setVisible(last)
        self.next_btn.setEnabled(self._can_continue(idx))
        for i in range(self.step_list.count()):
            self.step_list.item(i).setText(
                ("✓ " if (i < idx and self._step_done(i)) else "") + STEPS[i]
            )

    def _step_done(self, i: int) -> bool:
        if i == 0:
            return self.prep_page.is_ready()
        if i in (1, 2):
            return bool(self.state.source_dir)
        return False

    def _can_continue(self, idx: int) -> bool:
        if idx == 0:
            return self.prep_page.is_ready()
        if idx == 1:
            return bool(self.state.background_src) and bool(self.state.source_dir)
        if idx == 2:
            return bool(self.state.source_dir)
        return True

    def _on_upload_finished(self, ok: bool) -> None:
        if ok:
            self.finish_btn.setText("完成")
