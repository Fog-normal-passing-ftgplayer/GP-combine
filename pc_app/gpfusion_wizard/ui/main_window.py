"""向导主窗口：左侧步骤栏 + 右侧内容页。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
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
from .lite_source_page import LiteSourcePage
from .lite_uf2_page import LiteUf2Page
from .lite_webconfig_page import LiteWebConfigPage
from .pico_config_page import PicoConfigPage
from .prep_page import PrepPage
from .upload_page import UploadPage
from .webconfig_page import WebConfigPage

FULL_STEPS = [
    "连接与准备",
    "网页配置",
    "背景图",
    "按键布局",
    "Pico 配置",
    "GIF 动画",
    "编译上传",
]

LITE_STEPS = [
    "源码文件夹",
    "网页配置",
    "自定义布局",
    "生成 UF2",
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
        side_l.addSpacing(10)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("正式版", "full")
        self.mode_combo.addItem("Lite 版本", "lite")
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        side_l.addWidget(self.mode_combo)
        side_l.addSpacing(10)

        self.step_list = QListWidget()
        self.step_list.setObjectName("Steps")
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
        self.webconfig_page = WebConfigPage(
            title="正式版 · 第 2 步：网页配置",
            hint=(
                "正式版 Pico 固件插电脑后，在游戏手柄状态下同时按住 "
                "S2 + B3 + B4（Start + X + Y）约 3 秒，会重启进入网页配置模式，"
                "USB 虚拟出 192.168.7.1 网卡。这里直接显示它的网页配置界面。"
            ),
        )
        self.bg_page = BackgroundPage(self.state)
        self.layout_page = LayoutPage(self.state)
        self.pico_page = PicoConfigPage(self.state)
        self.gif_page = GifPage(self.state)
        self.upload_page = UploadPage(self.state)
        self.lite_source_page = LiteSourcePage(self.state)
        self.lite_webconfig_page = LiteWebConfigPage()
        self.lite_layout_page = LayoutPage(self.state, lite=True)
        self.lite_uf2_page = LiteUf2Page(self.state)
        self.stack.addWidget(self.prep_page)
        self.stack.addWidget(self.webconfig_page)
        self.stack.addWidget(self.bg_page)
        self.stack.addWidget(self.layout_page)
        self.stack.addWidget(self.pico_page)
        self.stack.addWidget(self.gif_page)
        self.stack.addWidget(self.upload_page)
        self.stack.addWidget(self.lite_source_page)
        self.stack.addWidget(self.lite_webconfig_page)
        self.stack.addWidget(self.lite_layout_page)
        self.stack.addWidget(self.lite_uf2_page)
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
        self.lite_source_page.ready_changed.connect(self._update_nav)
        self.upload_page.finished_upload.connect(self._on_upload_finished)
        self.lite_uf2_page.finished_build.connect(self._on_lite_build_finished)
        self.step_list.currentRowChanged.connect(self._go_to)
        self._mode = "full"
        self._cur_row = 0
        self._apply_mode_steps()
        self._update_nav()

    # ---------- 导航 ----------

    def _mode_offset(self) -> int:
        return 0 if self._mode == "full" else 7

    def _mode_page_count(self) -> int:
        return len(FULL_STEPS) if self._mode == "full" else len(LITE_STEPS)

    def _apply_mode_steps(self) -> None:
        self.step_list.blockSignals(True)
        self.step_list.clear()
        for name in (FULL_STEPS if self._mode == "full" else LITE_STEPS):
            self.step_list.addItem(QListWidgetItem(name))
        self.step_list.blockSignals(False)

    def _on_mode_changed(self) -> None:
        self._mode = str(self.mode_combo.currentData())
        self._apply_mode_steps()
        self._go_to(0)

    def _go_to(self, row: int) -> None:
        row = max(0, min(row, self._mode_page_count() - 1))
        idx = self._mode_offset() + row
        cur_row = self._cur_row
        if cur_row >= 0 and row > cur_row and not self._can_continue(cur_row):
            return
        self._cur_row = row
        self.stack.setCurrentIndex(idx)
        if self._mode == "full" and row == 6:
            self.upload_page.on_shown()
        if self._mode == "lite" and row == 3:
            self.lite_uf2_page.on_shown()
        self._update_nav()

    def _go_back(self) -> None:
        self._go_to(self._cur_row - 1)

    def _go_next(self) -> None:
        self._go_to(self._cur_row + 1)

    def _update_nav(self) -> None:
        row = self._cur_row
        self.back_btn.setEnabled(row > 0)
        last = row == self._mode_page_count() - 1
        self.next_btn.setVisible(not last)
        self.finish_btn.setVisible(last)
        self.next_btn.setEnabled(self._can_continue(row))
        if self._mode == "lite":
            self.device_banner.setVisible(False)
        else:
            self.device_banner.setVisible(not bool(self.state.port))
        steps = FULL_STEPS if self._mode == "full" else LITE_STEPS
        for i in range(self.step_list.count()):
            self.step_list.item(i).setText(
                ("✓ " if (i < row and self._step_done(i)) else "") + steps[i]
            )

    def _step_done(self, i: int) -> bool:
        if self._mode == "lite":
            if i == 0:
                return self.lite_source_page.can_proceed()
            return bool(self.state.lite_source_dir)
        if i == 0:
            return self.prep_page.is_ready()
        if i in (1, 2, 3, 4, 5):
            return bool(self.state.source_dir)
        return False

    def _can_continue(self, idx: int) -> bool:
        if self._mode == "lite":
            if idx == 0:
                return self.lite_source_page.can_proceed()
            return bool(self.state.lite_source_dir)
        if idx == 0:
            return self.prep_page.can_proceed()
        if idx == 1:
            return bool(self.state.source_dir)
        if idx == 2:
            return bool(self.state.background_src) and bool(self.state.source_dir)
        if idx in (3, 4, 5):
            return bool(self.state.source_dir)
        return True

    def _on_upload_finished(self, ok: bool) -> None:
        if ok:
            self.finish_btn.setText("完成")

    def _on_lite_build_finished(self, ok: bool) -> None:
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
                self.webconfig_page,
                self.bg_page,
                self.layout_page,
                self.pico_page,
                self.gif_page,
                self.lite_source_page,
                self.lite_webconfig_page,
                self.lite_layout_page,
                self.lite_uf2_page,
            ):
                page.reload_state()
            self._update_nav()
            QMessageBox.information(self, "导入成功", "\n".join(notes))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "导入失败", "无法读取备份文件：\n%s" % exc)
