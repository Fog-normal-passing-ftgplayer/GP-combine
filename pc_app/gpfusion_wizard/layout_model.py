"""按键布局数据模型。

向导统一生成一个「自定义」布局（机内第 4 个布局选项）：
4 个移动键 + 右侧按键（可增删）+ 可选的街机摇杆。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Btn:
    mask: int
    x: int
    y: int
    r: int              # 圆 = 半径；方 = 边长的一半
    square: bool        # True = 方块（WASD 风格），False = 圆环
    label: str          # 固定文字，不可自定义
    dpad: bool          # True = 方向键位，False = 功能键位

    @property
    def shape_name(self) -> str:
        return "方形" if self.square else "圆形"

    @property
    def size_text(self) -> str:
        return "边长 %d" % (self.r * 2) if self.square else "半径 %d" % self.r


@dataclass
class Lever:
    x: int = 38
    y: int = 80
    ring: int = 22
    knob: int = 7


@dataclass
class Layout:
    move: list[Btn] = field(default_factory=list)
    cluster: list[Btn] = field(default_factory=list)
    lever: Lever = field(default_factory=Lever)
    show_lever: bool = False

    @classmethod
    def preset(cls) -> "Layout":
        """默认自定义布局：移动键用 HITBOX 位形，右侧 8 键，不带摇杆。"""
        move = [
            Btn(0x04, 17, 44, 13, False, "L", True),
            Btn(0x02, 54, 44, 13, False, "D", True),
            Btn(0x08, 86, 66, 13, False, "R", True),
            Btn(0x01, 97, 120, 13, False, "U", True),
        ]
        cluster = [
            Btn(0x0004, 110, 48, 13, False, "B3", False),
            Btn(0x0008, 146, 36, 13, False, "B4", False),
            Btn(0x0020, 182, 36, 13, False, "R1", False),
            Btn(0x0010, 218, 48, 13, False, "L1", False),
            Btn(0x0001, 110, 86, 13, False, "B1", False),
            Btn(0x0002, 146, 74, 13, False, "B2", False),
            Btn(0x0080, 182, 74, 13, False, "R2", False),
            Btn(0x0040, 218, 86, 13, False, "L2", False),
        ]
        return cls(move=move, cluster=cluster, lever=Lever())

    def to_dict(self) -> dict[str, Any]:
        return {
            "move": [asdict(b) for b in self.move],
            "cluster": [asdict(b) for b in self.cluster],
            "lever": asdict(self.lever),
            "show_lever": self.show_lever,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Layout":
        p = cls.preset()

        def parse_btn(x: Any) -> Btn | None:
            if not isinstance(x, dict):
                return None
            try:
                mask = int(x.get("mask", 0))
                label = str(x.get("label", ""))
                # 兼容旧版本：RT/R2 位置带的是 L2 位、LT/L2 位置带的是 R2 位，
                # 标签位置是对的，纠正掩码（0x40=L2/LT、0x80=R2/RT）
                if mask == 0x40 and label in ("R2", "RT"):
                    mask = 0x80
                elif mask == 0x80 and label in ("L2", "LT"):
                    mask = 0x40
                return Btn(
                    mask=mask,
                    x=int(x.get("x", 0)),
                    y=int(x.get("y", 0)),
                    r=int(x.get("r", 10)),
                    square=bool(x.get("square", False)),
                    label=label,
                    dpad=bool(x.get("dpad", False)),
                )
            except Exception:
                return None

        def parse_list(
            key: str, fallback: list[Btn], exact: bool = True
        ) -> list[Btn]:
            raw = d.get(key)
            if not isinstance(raw, list):
                return fallback
            out = [b for b in (parse_btn(v) for v in raw) if b is not None]
            if exact:
                return out if len(out) == len(fallback) else fallback
            return out if out else fallback

        # 兼容旧版本数据：旧的 hitbox/wasd 分别映射到新的统一 move
        if "move" not in d and isinstance(d.get("hitbox"), list):
            d = dict(d)
            d["move"] = d["hitbox"]
        p.move = parse_list("move", p.move)
        p.cluster = parse_list("cluster", p.cluster, exact=False)
        ld = d.get("lever")
        if isinstance(ld, dict):
            try:
                p.lever = Lever(
                    x=int(ld.get("x", 38)),
                    y=int(ld.get("y", 80)),
                    ring=int(ld.get("ring", 22)),
                    knob=int(ld.get("knob", 7)),
                )
            except Exception:
                pass
        p.show_lever = bool(d.get("show_lever", False))
        return p
GROUP_MOVE = "move"
GROUP_CLUSTER = "cluster"
GROUP_LEVER = "lever"

# 可额外添加的按键（掩码与 GP2040-CE GamepadState.h 一致，随 UART 全 16 位传递）
EXTRA_BUTTONS: list[tuple[str, int]] = [
    ("L3", 0x0400),
    ("R3", 0x0800),
    ("S1", 0x0100),
    ("S2", 0x0200),
    ("A1", 0x1000),
    ("A2", 0x2000),
    ("A3", 0x4000),
    ("A4", 0x8000),
]


def find_free_spot(layout: Layout) -> tuple[int, int]:
    """在右侧区域找一个不与现有按键重叠的默认放置点。"""
    occupied = (
        [(b.x, b.y) for b in layout.move]
        + [(b.x, b.y) for b in layout.cluster]
    )
    for y in (105, 80, 55, 120, 90, 70):
        for x in (110, 134, 158, 182, 206, 226):
            if all((x - ox) ** 2 + (y - oy) ** 2 > 24 ** 2 for ox, oy in occupied):
                return x, y
    return 110, 105
