"""Lite 模式第 2 步：内嵌显示 192.168.7.1 的网页配置。"""
from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

WEB_CONFIG_URL = "http://192.168.7.1"

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView

    HAS_WEBENGINE = True
except Exception:  # noqa: BLE001
    HAS_WEBENGINE = False


class LiteWebConfigPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 12)
        title = QLabel("Lite 版本 · 第 2 步：网页配置")
        title.setObjectName("StepTitle")
        root.addWidget(title)
        hint = QLabel(
            "Lite 固件插电脑后，USB 会虚拟出 192.168.7.1 网卡。"
            "这里直接显示它的网页配置界面。"
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        bar = QHBoxLayout()
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.reload)
        bar.addWidget(self.refresh_btn)
        self.open_btn = QPushButton("在系统浏览器打开")
        self.open_btn.clicked.connect(self.open_external)
        bar.addWidget(self.open_btn)
        bar.addStretch(1)
        root.addLayout(bar)

        self.status = QLabel("")
        self.status.setObjectName("Muted")
        root.addWidget(self.status)

        if HAS_WEBENGINE:
            self.view = QWebEngineView()
            root.addWidget(self.view, 1)
        else:
            self.view = None
            root.addWidget(
                QLabel("未安装 QtWebEngine，请点「在系统浏览器打开」。")
            )

    def reload(self) -> None:
        if self.view is not None:
            self.view.load(QUrl(WEB_CONFIG_URL))
            self.status.setText("正在加载 %s …" % WEB_CONFIG_URL)
            self.status.setStyleSheet("color: #8E9BAD;")

    def open_external(self) -> None:
        QDesktopServices.openUrl(QUrl(WEB_CONFIG_URL))

    def reload_state(self) -> None:
        pass
