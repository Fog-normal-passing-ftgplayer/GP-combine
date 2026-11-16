"""向导主窗口：顶部品牌栏 + 左侧步骤栏 + 底部状态栏。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
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
from .sim_page import SimPage
from .layout_page import LayoutPage
from .lite_source_page import LiteSourcePage
from .lite_uf2_page import LiteUf2Page
from .lite_webconfig_page import LiteWebConfigPage
from .nes_page import NesPage
from .prep_page import PrepPage
from .reflash_page import ReflashPage
from .upload_page import UploadPage
from .webconfig_page import WebConfigPage

FULL_STEPS = [
    "设备与源码",
    "背景 / 壁纸",
    "按键布局",
    "GIF 动画",
    "小游戏（NES）",
    "网页配置",
    "仿真器预览",
    "编译上传",
    "整机重刷",
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
        self.resize(1320, 760)
        self.setObjectName("Root")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---------- 顶部品牌栏 ----------
        header = QWidget()
        header.setObjectName("Header")
        header.setFixedHeight(68)
        head = QHBoxLayout(header)
        head.setContentsMargins(20, 0, 20, 0)
        head.setSpacing(12)

        logo = QLabel("GP")
        logo.setObjectName("Logo")
        logo.setFixedSize(36, 36)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        head.addWidget(logo)

        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(1)
        app_title = QLabel("GP-Combine")
        app_title.setObjectName("AppTitle")
        app_sub = QLabel("配置助手")
        app_sub.setObjectName("AppSub")
        title_box.addWidget(app_title)
        title_box.addWidget(app_sub)
        head.addLayout(title_box)

        version = QLabel("v%s" % APP_VERSION)
        version.setObjectName("VersionChip")
        version.setFixedHeight(26)
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        head.addWidget(version)
        head.addStretch(1)

        self.mode_combo = QComboBox()
        self.mode_combo.setObjectName("ModeCombo")
        self.mode_combo.addItem("正式版", "full")
        self.mode_combo.addItem("Lite 版本", "lite")
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        head.addWidget(self.mode_combo)

        export_btn = QPushButton("导出配置")
        export_btn.setObjectName("Ghost")
        export_btn.clicked.connect(self._export_config)
        head.addWidget(export_btn)

        import_btn = QPushButton("导入配置")
        import_btn.setObjectName("Ghost")
        import_btn.clicked.connect(self._import_config)
        head.addWidget(import_btn)

        outer.addWidget(header)

        # ---------- 主体：侧栏 + 内容 ----------
        body = QWidget()
        root = QHBoxLayout(body)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(232)
        side_l = QVBoxLayout(sidebar)
        side_l.setContentsMargins(14, 18, 14, 14)
        side_l.setSpacing(6)

        nav_caption = QLabel("配 置 流 程")
        nav_caption.setObjectName("NavCaption")
        side_l.addWidget(nav_caption)
        side_l.addSpacing(2)

        self.step_list = QListWidget()
        self.step_list.setObjectName("Steps")
        self.step_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        side_l.addWidget(self.step_list, 1)

        root.addWidget(sidebar)

        content = QWidget()
        content.setObjectName("Content")
        content_l = QVBoxLayout(content)
        content_l.setContentsMargins(24, 20, 24, 20)
        content_l.setSpacing(0)

        self.stack = QStackedWidget()
        self.prep_page = PrepPage(self.state)
        self.webconfig_page = WebConfigPage(
            title="网页配置",
            hint=(
                "正式版 Pico 固件插电脑后，在游戏手柄状态下同时按住 "
                "S2 + B3 + B4（Start + X + Y）约 3 秒，会重启进入网页配置模式，"
                "USB 虚拟出 192.168.7.1 网卡。这里直接显示它的网页配置界面。"
            ),
        )
        self.bg_page = BackgroundPage(self.state)
        self.layout_page = LayoutPage(self.state)
        self.gif_page = GifPage(self.state)
        self.sim_page = SimPage(self.state)
        self.nes_page = NesPage(self.state)
        self.upload_page = UploadPage(self.state)
        self.reflash_page = ReflashPage(self.state)
        self.lite_source_page = LiteSourcePage(self.state)
        self.lite_webconfig_page = LiteWebConfigPage()
        self.lite_layout_page = LayoutPage(self.state, lite=True)
        self.lite_uf2_page = LiteUf2Page(self.state)
        self.stack.addWidget(self.prep_page)
        self.stack.addWidget(self.bg_page)
        self.stack.addWidget(self.layout_page)
        self.stack.addWidget(self.gif_page)
        self.stack.addWidget(self.nes_page)
        self.stack.addWidget(self.webconfig_page)
        self.stack.addWidget(self.sim_page)
        self.stack.addWidget(self.upload_page)
        self.stack.addWidget(self.reflash_page)
        self.stack.addWidget(self.lite_source_page)
        self.stack.addWidget(self.lite_webconfig_page)
        self.stack.addWidget(self.lite_layout_page)
        self.stack.addWidget(self.lite_uf2_page)
        content_l.addWidget(self.stack, 1)
        root.addWidget(content, 1)
        outer.addWidget(body, 1)

        # ---------- 底部状态栏 ----------
        footer = QWidget()
        footer.setObjectName("Footer")
        footer.setFixedHeight(34)
        foot = QHBoxLayout(footer)
        foot.setContentsMargins(20, 0, 20, 0)
        foot.setSpacing(8)

        self.status_dot = QLabel("●")
        self.status_dot.setObjectName("StatusDot")
        self.status_text = QLabel("")
        self.status_text.setObjectName("StatusText")
        foot.addWidget(self.status_dot)
        foot.addWidget(self.status_text)
        foot.addStretch(1)
        foot_hint = QLabel("GP-Combine · 桌面配置助手")
        foot_hint.setObjectName("FooterHint")
        foot.addWidget(foot_hint)
        outer.addWidget(footer)

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
        return 0 if self._mode == "full" else len(FULL_STEPS)

    def _mode_page_count(self) -> int:
        return len(FULL_STEPS) if self._mode == "full" else len(LITE_STEPS)

    def _apply_mode_steps(self) -> None:
        self.step_list.blockSignals(True)
        self.step_list.clear()
        for i, name in enumerate(FULL_STEPS if self._mode == "full" else LITE_STEPS):
            self.step_list.addItem(QListWidgetItem("%02d   %s" % (i + 1, name)))
        self.step_list.blockSignals(False)

    def _on_mode_changed(self) -> None:
        self._mode = str(self.mode_combo.currentData())
        self._apply_mode_steps()
        self._go_to(0)

    def _go_to(self, row: int) -> None:
        row = max(0, min(row, self._mode_page_count() - 1))
        idx = self._mode_offset() + row
        self._cur_row = row
        self.stack.setCurrentIndex(idx)
        if self._mode == "full" and row == 6:
            self.sim_page.on_shown()
        if self._mode == "full" and row == 7:
            self.upload_page.on_shown()
        if self._mode == "full" and row == 8:
            self.reflash_page.on_shown()
        if self._mode == "lite" and row == 3:
            self.lite_uf2_page.on_shown()
        self._update_nav()

    def _update_nav(self) -> None:
        if self._mode == "lite":
            dot, text = "#8B95A7", "Lite 模式 · 只生成 UF2，不写入设备"
        elif self.state.port:
            dot, text = "#3DDC97", "ESP32-S3 已连接"
        else:
            dot, text = "#FFB454", "未检测到 ESP32-S3 · 可预览和编辑，插入后重试上传"
        self.status_dot.setStyleSheet("color: %s;" % dot)
        self.status_text.setText(text)

    def _step_done(self, i: int) -> bool:
        if self._mode == "lite":
            if i == 0:
                return self.lite_source_page.can_proceed()
            return bool(self.state.lite_source_dir)
        if i == 0:
            return self.prep_page.is_ready()
        if i in (1, 2, 3, 4, 5):
            return bool(self.state.source_dir)
        if i == 6:          # 仿真器预览：可选步骤，不影响放行
            return True
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
        if idx in (3, 4, 5, 6):
            return bool(self.state.source_dir)
        return True

    def _on_upload_finished(self, ok: bool) -> None:
        pass   # 自由布局：不再有"完成"按钮

    def _on_lite_build_finished(self, ok: bool) -> None:
        pass

    # ---------- 配置备份 ----------

    def _export_config(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出配置备份",
            str(Path.home() / "gp-fusion-config.json"),
            "GP-Combine 配置 (*.json)",
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
            "GP-Combine 配置 (*.json)",
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
                self.gif_page,
                self.sim_page,
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
