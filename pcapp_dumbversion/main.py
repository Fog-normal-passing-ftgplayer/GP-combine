#!/usr/bin/env python3
"""GP-Combine 懒人版配置助手 —— 入口。

懒人包（离线）和开发模式用的是同一份代码：

    python3 main.py                # 打开界面（自动探测包结构）
    python3 main.py --selftest      # 只做环境自检，不开界面
    python3 main.py --bundle /path  # 指定懒人包根目录
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 打包成 exe（PyInstaller）后 __file__ 可能不存在，退回到 _MEIPASS
_HERE = Path(__file__).resolve().parent if "__file__" in globals() else Path(
    getattr(sys, "_MEIPASS", ".")
)
sys.path.insert(0, str(_HERE))


def _utf8_stdio() -> None:
    """Windows 控制台默认 cp1252，日志里的 ✔ / ✘ 会直接抛 UnicodeEncodeError。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass


def main() -> int:
    _utf8_stdio()
    parser = argparse.ArgumentParser(description="GP-Combine 懒人版配置助手")
    parser.add_argument("--bundle", default="", help="懒人包根目录（默认自动探测）")
    parser.add_argument("--selftest", action="store_true", help="只做环境自检")
    args = parser.parse_args()

    from dumb import bundle_env

    env = bundle_env.init(args.bundle or None)
    if args.selftest:
        return bundle_env.selftest(env)

    from dumb import ui

    return ui.run(env)


if __name__ == "__main__":
    raise SystemExit(main())
