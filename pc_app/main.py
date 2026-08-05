#!/usr/bin/env python3
"""GP-Fusion 配置向导入口（开发运行：python main.py）。"""
from __future__ import annotations

import sys

from gpfusion_wizard.ui.main import run, smoke_test


if __name__ == "__main__":
    if "--smoke" in sys.argv:
        sys.exit(smoke_test())
    sys.exit(run())
