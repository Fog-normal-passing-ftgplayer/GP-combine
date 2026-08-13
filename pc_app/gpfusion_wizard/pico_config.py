"""生成正式版 Pico 的用户配置头 pico_user.h（热键 + WS2812B）。"""
from __future__ import annotations

from pathlib import Path

# 标准按钮：标签 -> (GAMEPAD_MASK, 默认 GPIO)
BUTTONS: list[tuple[str, int, int]] = [
    ("UP", 0x0001, 2), ("DOWN", 0x0002, 3), ("RIGHT", 0x0008, 4), ("LEFT", 0x0004, 5),
    ("B1", 0x0001, 6), ("B2", 0x0002, 7), ("R2", 0x0080, 8), ("L2", 0x0040, 9),
    ("B3", 0x0004, 10), ("B4", 0x0008, 11), ("R1", 0x0020, 12), ("L1", 0x0010, 13),
    ("S1", 0x0100, 16), ("S2", 0x0200, 17), ("L3", 0x0400, 18), ("R3", 0x0800, 19),
    ("A1", 0x1000, 20), ("A2", 0x2000, 21),
]
BUTTON_MASK = {b: m for b, m, _ in BUTTONS}

# 常用热键动作：中文名 -> GamepadHotkey 枚举值
HOTKEY_ACTIONS: list[tuple[str, int]] = [
    ("HOME 键", 4),
    ("截图键", 5),
    ("SOCD=UP优先", 6),
    ("SOCD=中立", 7),
    ("SOCD=后输入", 8),
    ("SOCD=先输入", 11),
    ("SOCD=直通", 12),
    ("反向X", 9),
    ("反向Y", 10),
    ("四向模式切换", 13),
    ("载入配置档1", 15),
    ("载入配置档2", 16),
    ("载入配置档3", 17),
    ("载入配置档4", 18),
    ("下一配置档", 35),
    ("上一配置档", 42),
    ("保存配置", 43),
    ("默认模式重启", 22),
]

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
    hotkeys: list[dict],
    led_pin: int,
    leds_per_button: int,
    led_order: dict,
) -> str:
    lines: list[str] = []
    lines.append("#pragma once")
    lines.append("// 由 GP-Combine 配置助手生成：热键 + WS2812B 配置，请勿手改。")
    lines.append("")
    # 热键：最多 16 个槽位
    for i in range(16):
        if i < len(hotkeys) and hotkeys[i]:
            hk = hotkeys[i]
            action = int(hk.get("action", 0))
            button = str(hk.get("button", "S2"))
            mask = BUTTON_MASK.get(button, 0x0200)
            slot = "%02d" % (i + 1)
            lines.append("#define HOTKEY_%s_AUX_MASK 0" % slot)
            lines.append("#define HOTKEY_%s_BUTTONS_MASK 0x%04X  // %s"
                         % (slot, mask, button))
            lines.append("#define HOTKEY_%s_DPAD_MASK 0" % slot)
            lines.append("#define HOTKEY_%s_ACTION %d" % (slot, action))
            lines.append("")
        else:
            slot = "%02d" % (i + 1)
            lines.append("#define HOTKEY_%s_AUX_MASK 0" % slot)
            lines.append("#define HOTKEY_%s_BUTTONS_MASK 0" % slot)
            lines.append("#define HOTKEY_%s_DPAD_MASK 0" % slot)
            lines.append("#define HOTKEY_%s_ACTION 0" % slot)
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
