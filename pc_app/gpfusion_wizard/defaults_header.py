"""生成 esp32/defaults.h：机内默认按键布局。"""
from __future__ import annotations

from pathlib import Path


def generate_defaults_header(default_layout: int) -> str:
    return (
        "#pragma once\n"
        "// GP-Fusion 默认按键布局（由 PC 配置向导生成，请勿手改）。\n"
        "// 0=街机 1=HITBOX 2=WASD 3=自定义\n"
        "#define DEFAULT_LAYOUT %d\n" % int(default_layout)
    )


def write_defaults_header(default_layout: int, out_path: str | Path) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(generate_defaults_header(default_layout), encoding="utf-8")
    return out
