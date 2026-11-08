"""GP-Fusion 配置向导入口。"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from ..app_config import APP_NAME
from ..layout_header import generate_layout_header
from ..layout_model import Layout
from ..wizard_state import WizardState
from .main_window import MainWindow
from .theme import STYLE


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(STYLE)
    state = WizardState.load()
    win = MainWindow(state)
    win.show()
    return app.exec()


def smoke_test() -> int:
    """无界面自检：验证关键生成逻辑可运行。"""
    from pathlib import Path
    import tempfile

    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    state = WizardState.load()
    win = MainWindow(state)

    layout = Layout.preset()
    text = generate_layout_header(layout)
    assert "USER_MOVE" in text and "USER_SHOW_LEVER 0" in text
    assert "USER_LEVER_KNOB 7" in text

    from ..defaults_header import generate_defaults_header
    dh = generate_defaults_header(3)
    assert "#define DEFAULT_LAYOUT 3" in dh

    with tempfile.TemporaryDirectory() as tmp:
        from ..imagegen import generate_background_header
        from PIL import Image
        img = Image.new("RGB", (480, 270), (200, 30, 40))
        img_path = Path(tmp, "bg.png")
        img.save(img_path)
        out = Path(tmp, "background.h")
        generate_background_header(img_path, out)
        assert out.stat().st_size > 1000

    win.close()
    return 0
