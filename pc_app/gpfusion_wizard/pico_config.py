"""生成正式版 Pico 的用户配置头 pico_user.h（WS2812B 灯带）。

热键与灯序（按键→LED 顺序）均已改由设备端网页配置（192.168.7.1）完成，
不再写入 pico_user.h；灯序在固件里使用 BoardConfig 默认值，运行时由 webconfig 覆盖。
"""
from __future__ import annotations

from pathlib import Path


def generate_pico_user_header(
    led_pin: int,
    leds_per_button: int,
) -> str:
    lines: list[str] = []
    lines.append("#pragma once")
    lines.append("// 由 GP-Combine 配置助手生成：WS2812B 配置，请勿手改。")
    lines.append("// 热键/灯序请在设备网页配置（192.168.7.1）中设置。")
    lines.append("")
    # LED
    lines.append("#define BOARD_LEDS_PIN %d" % led_pin)
    lines.append("#define LEDS_PER_PIXEL %d" % max(1, leds_per_button))
    lines.append("#define LED_FORMAT LED_FORMAT_GRB")
    lines.append("")
    return "\n".join(lines)


def write_pico_user_header(out_path: str | Path, **kwargs) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(generate_pico_user_header(**kwargs), encoding="utf-8")
    return out
