"""向导主窗口：左侧步骤栏 + 右侧内容页。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..app_config import APP_NAME, APP_VERSION
from ..config_backup import export_config, import_config
from ..wizard_state import WizardState
from .background_page import BackgroundPage
from .gif_page import GifPage
from .layout_page import LayoutPage
from .pico_config_page import PicoConfigPage
from .prep_page import PrepPage
from .upload_page import UploadPage

STEPS = [
    "连接与准备",
    "背景图",
    "按键布局",
    "Pico 配置",
    "GIF 动画",
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
        app_sub = QLabel("配置向导")
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
        side_l.addSpacing(8)
        export_btn = QPushButton("导出配置…")
        export_btn.clicked.connect(self._export_config)
        side_l.addWidget(export_btn)
        import_btn = QPushButton("导入配置…")
        import_btn.clicked.connect(self._import_config)
        side_l.addWidget(import_btn)
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
        self.pico_page = PicoConfigPage(self.state)
        self.gif_page = GifPage(self.state)
        self.upload_page = UploadPage(self.state)
        self.stack.addWidget(self.prep_page)
        self.stack.addWidget(self.bg_page)
        self.stack.addWidget(self.layout_page)
        self.stack.addWidget(self.pico_page)
        self.stack.addWidget(self.gif_page)
        self.stack.addWidget(self.upload_page)
        root.addWidget(self.stack, 1)
        outer.addWidget(body, 1)

        # 未插设备的提示条
        self.device_banner = QLabel(
            "未插入 ESP32-S3：可以预览/编辑，但不会写入固件，插入后重试上传。"
        )
        self.device_banner.setStyleSheet(
            "background: #4A3200; color: #FFD27A; padding: 6px 16px; font-size: 13px;"
        )
        self.device_banner.setVisible(False)
        outer.addWidget(self.device_banner)

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
        if row == 5:
            self.upload_page.on_shown()
        self._update_nav()

    def _go_back(self) -> None:
        self._go_to(self.stack.currentIndex() - 1)

    def _go_next(self) -> None:
        self._go_to(self.stack.currentIndex() + 1)

    def _update_nav(self) -> None:
        idx = self.stack.currentIndex()
        self.device_banner.setVisible(not bool(self.state.port))
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
        if i in (1, 2, 3, 4):
            return bool(self.state.source_dir)
        return False

    def _can_continue(self, idx: int) -> bool:
        if idx == 0:
            return self.prep_page.can_proceed()
        if idx == 1:
            return bool(self.state.background_src) and bool(self.state.source_dir)
        if idx in (2, 3, 4):
            return bool(self.state.source_dir)
        return True

    def _on_upload_finished(self, ok: bool) -> None:
        if ok:
            self.finish_btn.setText("完成")

    # ---------- 配置备份 ----------

    def _export_config(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出配置备份",
            str(Path.home() / "gp-fusion-config.json"),
            "GP-Fusion 配置 (*.json)",
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            export_config(self.state, path)
            QMessageBox.information(self, "导出成功", "配置已导出到：\n%s" % path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "导出失败", str(exc))

    def _import_config(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "导入配置备份",
            str(Path.home()),
            "GP-Fusion 配置 (*.json)",
        )
        if not path:
            return
        try:
            new_state, notes = import_config(self.state, path)
            self.state.copy_from(new_state)
            self.state.save()
            for page in (
                self.prep_page,
                self.bg_page,
                self.layout_page,
                self.pico_page,
                self.gif_page,
            ):
                page.reload_state()
            self._update_nav()
            QMessageBox.information(self, "导入成功", "\n".join(notes))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "导入失败", "无法读取备份文件：\n%s" % exc)
