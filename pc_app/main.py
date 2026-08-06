#!/usr/bin/env python3
"""GP-Fusion 配置向导入口（开发运行：python main.py）。"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

from gpfusion_wizard.ui.main import run, smoke_test


def _crash_log_path() -> Path:
    base = Path.cwd()
    # 优先写到程序旁边，便于打包后排查
    try:
        base = Path(sys.executable).resolve().parent
    except Exception:
        pass
    return base / "gpfusion_crash.log"


def _excepthook(etype, value, tb) -> None:
    """窗口版程序崩溃时不再静默退出：写日志 + 弹窗提示。"""
    msg = "".join(traceback.format_exception(etype, value, tb))
    try:
        _crash_log_path().write_text(msg, encoding="utf-8")
    except Exception:
        pass
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance() or QApplication(sys.argv)
        box = QMessageBox()
        box.setWindowTitle("GP-Fusion 启动失败")
        box.setText("程序启动时发生错误，详情已写入：\n%s" % _crash_log_path())
        box.setDetailedText(msg)
        box.exec()
    except Exception:
        pass
    sys.exit(1)


if __name__ == "__main__":
    sys.excepthook = _excepthook
    if "--smoke" in sys.argv:
        sys.exit(smoke_test())
    sys.exit(run())
