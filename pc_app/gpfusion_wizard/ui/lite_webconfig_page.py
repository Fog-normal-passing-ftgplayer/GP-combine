"""Lite 模式：网页配置（复用通用 WebConfigPage）。"""
from __future__ import annotations

from .webconfig_page import WebConfigPage


class LiteWebConfigPage(WebConfigPage):
    def __init__(self, parent=None) -> None:
        super().__init__(
            title="Lite 版本 · 网页配置",
            hint=(
                "Lite 固件插电脑后，USB 会虚拟出 192.168.7.1 网卡。"
                "这里直接显示它的网页配置界面。"
            ),
            parent=parent,
        )
