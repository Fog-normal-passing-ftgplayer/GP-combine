"""把 Layout 模型生成 esp32/layout_user.h。"""
from __future__ import annotations

from pathlib import Path

from .layout_model import Btn, Layout


def _fmt_mask(mask: int) -> str:
    return "0x%08X" % mask


def _btn_line(b: Btn) -> str:
    square = 1 if b.square else 0
    dpad = 1 if b.dpad else 0
    return '  {%s, %d, %d, %d, "%s", %d, %d},' % (
        _fmt_mask(b.mask), b.x, b.y, b.r, b.label, dpad, square,
    )


def generate_layout_header(layout: Layout) -> str:
    lines: list[str] = []
    lines.append("#pragma once")
    lines.append("// GP-Fusion 用户按键布局 — 由 GP-Fusion 配置向导自动生成，请勿手改。")
    lines.append('#include "menu.h"')
    lines.append("")
    lines.append("#define USER_LAYOUT 1")
    lines.append("#define USER_SHOW_LEVER %d" % (1 if layout.show_lever else 0))
    lines.append("")
    lines.append("static const LayoutBtn USER_MOVE[] = {")
    lines += [_btn_line(b) for b in layout.move]
    lines.append("};")
    lines.append("")
    lines.append("static const LayoutBtn USER_CLUSTER[] = {")
    lines += [_btn_line(b) for b in layout.cluster]
    lines.append("};")
    lines.append("")
    lines.append("#define USER_LEVER_X %d" % layout.lever.x)
    lines.append("#define USER_LEVER_Y %d" % layout.lever.y)
    lines.append("#define USER_LEVER_RING %d" % layout.lever.ring)
    lines.append("#define USER_LEVER_KNOB %d" % layout.lever.knob)
    lines.append("")
    return "\n".join(lines)


def write_layout_header(layout: Layout, out_path: Path) -> None:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(generate_layout_header(layout), encoding="utf-8")
