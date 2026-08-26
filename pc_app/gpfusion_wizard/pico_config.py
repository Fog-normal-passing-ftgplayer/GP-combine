"""生成正式版 Pico 的用户配置头 pico_user.h（WS2812B 灯带）。

热键配置已改由设备端网页配置（192.168.7.1）完成，不再写入 pico_user.h。
"""
from __future__ import annotations

from pathlib import Path

# 按键顺序（LED 灯索引默认值，与 configs/GPFusion/BoardConfig.h 一致）
DEFAULT_LED_ORDER: list[tuple[str, int]] = [
    ("DPAD_LEFT", 0), ("DPAD_DOWN", 1), ("DPAD_RIGHT", 2), ("DPAD_UP", 3),
    ("B3", 4), ("B4", 5), ("R1", 6), ("L1", 7),
    ("B1", 8), ("B2", 9), ("R2", 10), ("L2", 11),
    ("A1", 12), ("L3", 13), ("R3", 14), ("A2", 15),
]

# 界面按键名 -> 固件 neopicoleds.h 期望的宏名（LEDS_BUTTON_* / LEDS_DPAD_*）
LED_MACROS: dict[str, str] = {
    "DPAD_LEFT": "LEDS_DPAD_LEFT", "DPAD_DOWN": "LEDS_DPAD_DOWN",
    "DPAD_RIGHT": "LEDS_DPAD_RIGHT", "DPAD_UP": "LEDS_DPAD_UP",
    "B1": "LEDS_BUTTON_B1", "B2": "LEDS_BUTTON_B2", "B3": "LEDS_BUTTON_B3",
    "B4": "LEDS_BUTTON_B4", "R1": "LEDS_BUTTON_R1", "L1": "LEDS_BUTTON_L1",
    "R2": "LEDS_BUTTON_R2", "L2": "LEDS_BUTTON_L2", "S1": "LEDS_BUTTON_S1",
    "S2": "LEDS_BUTTON_S2", "L3": "LEDS_BUTTON_L3", "R3": "LEDS_BUTTON_R3",
    "A1": "LEDS_BUTTON_A1", "A2": "LEDS_BUTTON_A2",
}


def generate_pico_user_header(
    led_pin: int,
    leds_per_button: int,
    led_order: dict,
) -> str:
    lines: list[str] = []
    lines.append("#pragma once")
    lines.append("// 由 GP-Combine 配置助手生成：WS2812B 配置，请勿手改。")
    lines.append("// 热键/按键映射请在设备网页配置（192.168.7.1）中设置。")
    lines.append("")
    # LED
    lines.append("#define BOARD_LEDS_PIN %d" % led_pin)
    lines.append("#define LEDS_PER_PIXEL %d" % max(1, leds_per_button))
    lines.append("#define LED_FORMAT LED_FORMAT_GRB")
    lines.append("")
    for name, default_idx in DEFAULT_LED_ORDER:
        idx = int(led_order.get(name, default_idx))
        macro = LED_MACROS.get(name, "LEDS_%s" % name)
        lines.append("#define %s %d" % (macro, idx))
    lines.append("")
    return "\n".join(lines)


def write_pico_user_header(out_path: str | Path, **kwargs) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(generate_pico_user_header(**kwargs), encoding="utf-8")
    return out
