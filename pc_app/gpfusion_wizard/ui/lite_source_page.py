"""Lite 模式第 1 步：选择 Lite 版本源码文件夹。"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..app_config import default_tool_dir
from ..jobs import JobRunner
from ..toolchain import git_available
from ..wizard_state import WizardState

PICO_SDK_URL = "https://github.com/raspberrypi/pico-sdk.git"
SCREEN_OPTIONS = [("0.96", "0.96 寸（SSD1306）"), ("1.3", "1.3 寸（SH1106）")]


def lite_source_ready(path: str) -> bool:
    if not path:
        return False
    p = Path(path)
    return (
        (p / "configs" / "GPFusionLite" / "BoardConfig.h").is_file()
        and (p / "src").is_dir()
    )


def default_pico_sdk_dir() -> Path:
    return default_tool_dir() / "pico-sdk"


def write_lite_display_header(source_dir: str, screen_size: str) -> None:
    """把屏幕尺寸写入 configs/GPFusionLite/lite_display.h（固件编译时读取）。"""
    if not lite_source_ready(source_dir):
        return
    label = "0.96 寸 SSD1306" if screen_size == "0.96" else "1.3 寸 SH1106"
    # 0.96 与 1.3 单色 I2C 屏均为 128x64，驱动自动识别控制器
    lines = [
        "#pragma once",
        "// 屏幕尺寸由配置助手生成，请勿手改。",
        "// 当前选择：%s（128x64）" % label,
        "#define LITE_DISPLAY_SIZE GPGFX_DisplaySize::SIZE_128x64",
        "",
    ]
    out = Path(source_dir) / "configs" / "GPFusionLite" / "lite_display.h"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")


class LiteSourcePage(QWidget):
    ready_changed = Signal()

    def __init__(self, state: WizardState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._runner: JobRunner | None = None
        self._build_ui()
        self._sync()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 12)
        title = QLabel("Lite 版本 · 第 1 步：源码文件夹")
        title.setObjectName("StepTitle")
        root.addWidget(title)
        hint = QLabel(
            "选择 Lite 版本的固件源码文件夹（包含 configs/GPFusionLite 和 src 的目录）。"
            "一般是 clone 下来的 GP-Combine 仓库，或者单独放 Lite 源码的文件夹。"
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        root.addWidget(hint)
        root.addSpacing(10)

        row = QHBoxLayout()
        self.path_label = QLabel("未选择")
        self.path_label.setObjectName("Muted")
        row.addWidget(self.path_label, 1)
        self.pick_btn = QPushButton("选择文件夹…")
        self.pick_btn.clicked.connect(self.pick)
        row.addWidget(self.pick_btn)
        root.addLayout(row)

        screen_row = QHBoxLayout()
        screen_row.addWidget(QLabel("屏幕尺寸"))
        self.screen_combo = QComboBox()
        for key, name in SCREEN_OPTIONS:
            self.screen_combo.addItem(name, key)
        self.screen_combo.currentIndexChanged.connect(self._on_screen_changed)
        screen_row.addWidget(self.screen_combo)
        screen_row.addStretch(1)
        root.addLayout(screen_row)

        root.addSpacing(12)
        deps = QGroupBox("Lite 构建依赖")
        deps_l = QVBoxLayout(deps)

        sdk_row = QHBoxLayout()
        sdk_row.addWidget(QLabel("pico-sdk"))
        self.sdk_status = QLabel("检测中…")
        self.sdk_status.setObjectName("Muted")
        sdk_row.addWidget(self.sdk_status)
        sdk_row.addStretch(1)
        self.sdk_btn = QPushButton("安装")
        self.sdk_btn.clicked.connect(self.install_pico_sdk)
        sdk_row.addWidget(self.sdk_btn)
        deps_l.addLayout(sdk_row)

        self.sdk_bar = QProgressBar()
        self.sdk_bar.setVisible(False)
        deps_l.addWidget(self.sdk_bar)

        tool_row = QHBoxLayout()
        tool_row.addWidget(QLabel("cmake / make / ARM 工具链 / Node"))
        self.tools_status = QLabel("检测中…")
        self.tools_status.setObjectName("Muted")
        tool_row.addWidget(self.tools_status)
        tool_row.addStretch(1)
        hint_btn = QPushButton("安装提示")
        hint_btn.clicked.connect(self.show_tools_hint)
        tool_row.addWidget(hint_btn)
        deps_l.addLayout(tool_row)

        root.addWidget(deps)

        self.status = QLabel("")
        self.status.setObjectName("Muted")
        root.addWidget(self.status)
        root.addStretch(1)

    def _sync(self) -> None:
        path = self.state.lite_source_dir
        if lite_source_ready(path):
            self.path_label.setText(path)
            self.status.setText("✔ 源码目录有效")
            self.status.setStyleSheet("color: #64E0A0;")
        elif path:
            self.path_label.setText(path)
            self.status.setText("目录无效：找不到 configs/GPFusionLite 或 src")
            self.status.setStyleSheet("color: #FF7B72;")
        else:
            self.path_label.setText("未选择")
            self.status.setText("")
        idx = self.screen_combo.findData(self.state.lite_screen_size)
        self.screen_combo.blockSignals(True)
        self.screen_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.screen_combo.blockSignals(False)
        write_lite_display_header(path, self.state.lite_screen_size)
        self.ready_changed.emit()

        # 依赖检测
        self._refresh_deps()

    def _refresh_deps(self) -> None:
        sdk = self._find_pico_sdk()
        if sdk:
            self.state.pico_sdk_dir = str(sdk)
            self.sdk_status.setText("已就绪：%s" % sdk)
            self.sdk_status.setStyleSheet("color: #64E0A0;")
            self.sdk_btn.setText("重新安装")
        else:
            self.state.pico_sdk_dir = ""
            self.sdk_status.setText("未安装")
            self.sdk_status.setStyleSheet("color: #FFB454;")
            self.sdk_btn.setText("安装")
        self.state.save()

        missing = []
        for tool, name in (
            ("cmake", "cmake"),
            ("make", "make"),
            ("arm-none-eabi-gcc", "ARM 工具链"),
            ("node", "Node"),
            ("npm", "npm"),
        ):
            if shutil.which(tool):
                continue
            missing.append(name)
        if missing:
            self.tools_status.setText("缺少：%s" % "、".join(missing))
            self.tools_status.setStyleSheet("color: #FFB454;")
        else:
            self.tools_status.setText("全部就绪")
            self.tools_status.setStyleSheet("color: #64E0A0;")

    def _find_pico_sdk(self) -> Path | None:
        candidates: list[Path] = []
        if self.state.pico_sdk_dir:
            candidates.append(Path(self.state.pico_sdk_dir))
        env = os.environ.get("PICO_SDK_PATH")
        if env:
            candidates.append(Path(env))
        candidates.append(default_pico_sdk_dir())
        candidates.append(Path.home() / "pico" / "pico-sdk")
        for c in candidates:
            if (c / "pico_sdk_init.cmake").is_file():
                return c
        return None

    def install_pico_sdk(self) -> None:
        if self._runner is not None and self._runner.isRunning():
            return
        if not git_available():
            QMessageBox.warning(self, "缺少 git", "安装 pico-sdk 需要 git，请先安装 git。")
            return
        dest = default_pico_sdk_dir()
        dest.parent.mkdir(parents=True, exist_ok=True)
        self.sdk_btn.setEnabled(False)
        self.sdk_bar.setVisible(True)
        self.sdk_bar.setRange(0, 0)
        self.sdk_status.setText("正在下载 pico-sdk（含子模块，请耐心等待）…")
        self.sdk_status.setStyleSheet("color: #8E9BAD;")

        cmd = ["git", "clone", "--progress", "--recurse-submodules", PICO_SDK_URL, str(dest)]

        def on_done(code: int) -> None:
            self.sdk_btn.setEnabled(True)
            self.sdk_bar.setVisible(False)
            self._refresh_deps()
            if code == 0 and self._find_pico_sdk() is not None:
                QMessageBox.information(
                    self, "pico-sdk 已安装",
                    "已安装到：%s\nPICO_SDK_PATH 已自动设定，生成 UF2 时会使用。" % dest,
                )
            else:
                QMessageBox.warning(self, "安装失败", "pico-sdk 下载失败，请检查网络后重试。")

        runner = JobRunner()
        self._runner = runner
        runner.finished.connect(on_done)
        runner.start(cmd)

    def show_tools_hint(self) -> None:
        QMessageBox.information(
            self,
            "安装构建工具",
            "Lite 固件编译需要 cmake / make / ARM 工具链 / Node。\n\n"
            "Linux（Arch/Manjaro）：\n"
            "  sudo pacman -S cmake make arm-none-eabi-gcc nodejs npm git\n\n"
            "Linux（Debian/Ubuntu）：\n"
            "  sudo apt install cmake make gcc-arm-none-eabi nodejs npm git\n\n"
            "Windows：请安装 CMake、make（MinGW）、ARM GCC（arm-none-eabi）与 Node.js。",
        )

    def pick(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "选择 Lite 源码文件夹", self.state.lite_source_dir or str(Path.home())
        )
        if path:
            self.state.lite_source_dir = path
            self.state.save()
            self._sync()

    def _on_screen_changed(self) -> None:
        self.state.lite_screen_size = str(self.screen_combo.currentData())
        self.state.save()
        write_lite_display_header(self.state.lite_source_dir, self.state.lite_screen_size)
        self.ready_changed.emit()

    def can_proceed(self) -> bool:
        return lite_source_ready(self.state.lite_source_dir)

    def reload_state(self) -> None:
        self._sync()
