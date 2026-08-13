"""向导的共享状态与本地持久化。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from .app_config import state_file
from .layout_model import Layout


@dataclass
class WizardState:
    port: str = ""
    cli_path: str = ""
    source_dir: str = ""
    background_src: str = ""
    background_mode: str = "cover"
    default_layout: int = 1          # 0=街机 1=HITBOX 2=WASD 3=自定义
    # Pico 配置（正式版）
    hotkeys: list = field(default_factory=list)   # [{action, button}]
    led_pin: int = 28
    leds_per_button: int = 1
    led_order: dict = field(default_factory=dict) # {button: index}
    # GIF 动画（正式版 ESP32）
    gif_src: str = ""
    gif_mode: str = "cover"
    gif_palette: int = 16
    layout: Layout = field(default_factory=Layout.preset)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["version"] = 1
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "WizardState":
        s = cls()
        s.port = str(d.get("port", ""))
        s.cli_path = str(d.get("cli_path", ""))
        s.source_dir = str(d.get("source_dir", ""))
        s.background_src = str(d.get("background_src", ""))
        s.background_mode = str(d.get("background_mode", "cover"))
        try:
            s.default_layout = int(d.get("default_layout", 1))
        except Exception:
            s.default_layout = 1
        s.hotkeys = list(d.get("hotkeys", [])) or []
        try:
            s.led_pin = int(d.get("led_pin", 28))
            s.leds_per_button = int(d.get("leds_per_button", 1))
        except Exception:
            pass
        s.led_order = dict(d.get("led_order", {}))
        s.gif_src = str(d.get("gif_src", ""))
        s.gif_mode = str(d.get("gif_mode", "cover"))
        try:
            s.gif_palette = int(d.get("gif_palette", 16))
        except Exception:
            s.gif_palette = 16
        if isinstance(d.get("layout"), dict):
            try:
                s.layout = Layout.from_dict(d["layout"])
            except Exception:
                s.layout = Layout.preset()
        return s

    def save(self) -> None:
        try:
            state_file().parent.mkdir(parents=True, exist_ok=True)
            state_file().write_text(
                json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    @classmethod
    def load(cls) -> "WizardState":
        try:
            if state_file().exists():
                return cls.from_dict(json.loads(state_file().read_text(encoding="utf-8")))
        except Exception:
            pass
        return cls()

    def copy_from(self, other: "WizardState") -> None:
        """把另一份状态原地拷入（页面都持有同一个 state 引用，导入备份时用它）。"""
        self.__dict__.update(other.__dict__)


def source_ready(source_dir: str) -> bool:
    if not source_dir:
        return False
    p = Path(source_dir)
    return (p / "esp32" / "esp32.ino").is_file()
