"""把 Lite 布局（128x64 屏幕坐标空间）生成固件头文件（configs/GPFusionLite/layout_user.h）。

坐标 1:1 直出，所见即所得；顶部 8px 为状态栏区域。
"""
from __future__ import annotations

from pathlib import Path

from .layout_model import Btn, Layout


def generate_lite_layout_header(layout: Layout) -> str:
    def btn(b: Btn) -> str:
        square = 1 if b.square else 0
        dpad = 1 if b.dpad else 0
        return '  {0x%08X, %d, %d, %d, "%s", %d, %d},' % (
            b.mask, b.x, b.y, b.r, b.label, dpad, square,
        )

    lines: list[str] = []
    lines.append("#pragma once")
    lines.append("// GP-Combine Lite 用户按键布局 — 由配置助手自动生成，请勿手改。")
    lines.append("// 坐标为 128x64 屏幕空间，1:1 直出（顶部 8px 状态栏）。")
    lines.append("// 需要 LiteCustomLayoutScreen 提供 LiteLayoutBtn 类型")
    lines.append("#define LITE_USER_LAYOUT 1")
    lines.append("#define LITE_USER_SHOW_LEVER %d" % (1 if layout.show_lever else 0))
    lines.append("")
    lines.append("static const LiteLayoutBtn LITE_USER_MOVE[] = {")
    lines += [btn(b) for b in layout.move]
    lines.append("};")
    lines.append("")
    lines.append("static const LiteLayoutBtn LITE_USER_CLUSTER[] = {")
    lines += [btn(b) for b in layout.cluster]
    lines.append("};")
    lines.append("")
    lines.append("#define LITE_USER_LEVER_X %d" % layout.lever.x)
    lines.append("#define LITE_USER_LEVER_Y %d" % layout.lever.y)
    lines.append("#define LITE_USER_LEVER_RING %d" % layout.lever.ring)
    lines.append("#define LITE_USER_LEVER_KNOB %d" % layout.lever.knob)
    lines.append("")
    return "\n".join(lines)


def write_lite_layout_header(layout: Layout, out_path: Path) -> None:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(generate_lite_layout_header(layout), encoding="utf-8")
