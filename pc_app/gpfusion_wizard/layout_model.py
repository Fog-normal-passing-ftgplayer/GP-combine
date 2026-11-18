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


# 状态栏三个可移动元素。坐标是屏内逻辑像素，含义与固件画的时候一致：
#   text -> 文字左上角        batt -> 电池图标左上角
#   wifi -> 无线图标圆心（和固件的 drawMiniWireless 一致）
STATUS_TEXT = "text"
STATUS_BATT = "batt"
STATUS_WIFI = "wifi"
STATUS_KEYS: tuple[str, ...] = (STATUS_TEXT, STATUS_BATT, STATUS_WIFI)
STATUS_NAMES: dict[str, str] = {
    STATUS_TEXT: "状态栏文字",
    STATUS_BATT: "电量指示",
    STATUS_WIFI: "无线图标",
}


@dataclass
class StatusPos:
    text_x: int = 4
    text_y: int = 3
    batt_x: int = 198
    batt_y: int = 2
    wifi_x: int = 232
    wifi_y: int = 11

    def get(self, key: str) -> tuple[int, int]:
        if key == STATUS_TEXT:
            return self.text_x, self.text_y
        if key == STATUS_BATT:
            return self.batt_x, self.batt_y
        return self.wifi_x, self.wifi_y

    def set(self, key: str, x: int, y: int) -> None:
        if key == STATUS_TEXT:
            self.text_x, self.text_y = x, y
        elif key == STATUS_BATT:
            self.batt_x, self.batt_y = x, y
        elif key == STATUS_WIFI:
            self.wifi_x, self.wifi_y = x, y

    def is_default(self) -> bool:
        return self == StatusPos()


def status_defaults(width: int, height: int) -> StatusPos:
    """各分辨率在固件里的默认位置（layout_user.h 不覆盖时就用这些）。"""
    if width >= 300:          # 170x320 / 172x320：内容宽 320
        return StatusPos(text_x=4, text_y=3, batt_x=282, batt_y=2,
                         wifi_x=310, wifi_y=11)
    return StatusPos()        # 240x135


@dataclass
class Layout:
    move: list[Btn] = field(default_factory=list)
    cluster: list[Btn] = field(default_factory=list)
    lever: Lever = field(default_factory=Lever)
    show_lever: bool = False
    # 状态栏位置按分辨率分别保存：240 和 320 宽是两套完全不同的位置，
    # 共用一个值会在切分辨率时被夹到边缘（"240 错位"的根因）。
    status_by_res: dict[str, StatusPos] = field(default_factory=dict)

    def status_for(self, res: str, width: int, height: int) -> StatusPos:
        """取该分辨率的状态栏位置；没有就按该分辨率的默认值建一个。"""
        key = str(res or "")
        sp = self.status_by_res.get(key)
        if sp is None:
            sp = StatusPos()
            legacy = self.status_by_res.get(LEGACY_STATUS_KEY)
            if legacy is not None and width < 300 and legacy.batt_x < width:
                sp = StatusPos(**asdict(legacy))      # 旧版单值：只在小屏上沿用
            else:
                sp = status_defaults(width, height)
            self.status_by_res[key] = sp
        return sp

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

    @classmethod
    def preset_170x320(cls) -> "Layout":
        """竖屏变体默认布局：内容区 320×高 横屏，
        与固件 esp32_170x320 / esp32_172x320 的 HITBOX_MOVE/RIGHT_CLUSTER 一致。
        172 版内容高 172，下列坐标 y≤151 不溢出，直接复用。"""
        move = [
            Btn(0x04, 23, 55, 13, False, "L", True),
            Btn(0x02, 72, 55, 13, False, "D", True),
            Btn(0x08, 115, 83, 13, False, "R", True),
            Btn(0x01, 129, 151, 13, False, "U", True),
        ]
        cluster = [
            Btn(0x0004, 147, 60, 13, False, "B3", False),
            Btn(0x0008, 195, 45, 13, False, "B4", False),
            Btn(0x0020, 243, 45, 13, False, "R1", False),
            Btn(0x0010, 291, 60, 13, False, "L1", False),
            Btn(0x0001, 147, 108, 13, False, "B1", False),
            Btn(0x0002, 195, 93, 13, False, "B2", False),
            Btn(0x0080, 243, 93, 13, False, "R2", False),
            Btn(0x0040, 291, 108, 13, False, "L2", False),
        ]
        return cls(move=move, cluster=cluster,
                   lever=Lever(x=51, y=101, ring=22, knob=7))

    @classmethod
    def lite_preset(cls) -> "Layout":
        """Lite（128x64 屏，顶部 8px 状态栏）默认布局。

        坐标就是屏幕像素、1:1 写进固件头文件，不能再拿 240x135 的预设直接塞进来
        （以前「恢复默认」就是这么干的，128x64 屏上一半按键画不出来）。
        左侧十字方向键（开摇杆时会被摇杆顶掉）+ 右侧 2x4 功能键。
        """
        move = [
            Btn(0x01, 20, 21, 7, False, "U", True),
            Btn(0x04, 9, 36, 7, False, "L", True),
            Btn(0x08, 31, 36, 7, False, "R", True),
            Btn(0x02, 20, 51, 7, False, "D", True),
        ]
        cluster = [
            Btn(0x0004, 57, 21, 6, False, "B3", False),
            Btn(0x0008, 73, 21, 6, False, "B4", False),
            Btn(0x0020, 89, 21, 6, False, "R1", False),
            Btn(0x0010, 105, 21, 6, False, "L1", False),
            Btn(0x0001, 57, 41, 6, False, "B1", False),
            Btn(0x0002, 73, 41, 6, False, "B2", False),
            Btn(0x0080, 89, 41, 6, False, "R2", False),
            Btn(0x0040, 105, 41, 6, False, "L2", False),
        ]
        return cls(move=move, cluster=cluster,
                   lever=Lever(x=20, y=36, ring=11, knob=4))

    def to_dict(self) -> dict[str, Any]:
        return {
            "move": [asdict(b) for b in self.move],
            "cluster": [asdict(b) for b in self.cluster],
            "lever": asdict(self.lever),
            "show_lever": self.show_lever,
            "status_by_res": {k: asdict(v) for k, v in self.status_by_res.items()},
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Layout":
        p = cls.preset()

        # 状态栏位置：按分辨率分别保存
        def parse_status(v: Any) -> StatusPos | None:
            if not isinstance(v, dict):
                return None
            sp = StatusPos()
            for k in ("text_x", "text_y", "batt_x", "batt_y", "wifi_x", "wifi_y"):
                try:
                    setattr(sp, k, int(v.get(k, getattr(sp, k))))
                except (TypeError, ValueError):
                    pass
            return sp

        status_map: dict[str, StatusPos] = {}
        raw_map = d.get("status_by_res")
        if isinstance(raw_map, dict):
            for key, val in raw_map.items():
                sp = parse_status(val)
                if sp is not None:
                    status_map[str(key)] = sp
        legacy_status = parse_status(d.get("status"))   # 上一版只有一个全局值
        if legacy_status is not None and not status_map:
            status_map[LEGACY_STATUS_KEY] = legacy_status

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
        p.status_by_res = status_map
        return p


def fit_layout_to_screen(
    layout: Layout,
    width: int = 128,
    height: int = 64,
    status_h: int = 8,
) -> Layout:
    """把 240x135 布局按包围盒等比适配到指定屏幕（如 Lite 128x64）。

    返回新的 Layout，坐标已是目标屏幕空间（可直接 1:1 写入固件头文件）。
    """
    xs: list[int] = []
    ys: list[int] = []
    for b in list(layout.move) + list(layout.cluster):
        xs += [b.x - b.r, b.x + b.r]
        ys += [b.y - b.r, b.y + b.r]
    if layout.show_lever:
        xs += [layout.lever.x - layout.lever.ring, layout.lever.x + layout.lever.ring]
        ys += [layout.lever.y - layout.lever.ring, layout.lever.y + layout.lever.ring]
    if not xs:
        return Layout(
            move=layout.move,
            cluster=layout.cluster,
            lever=layout.lever,
            show_lever=layout.show_lever,
        )
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    bw, bh = max(1, maxx - minx), max(1, maxy - miny)
    s = min(width / bw, (height - status_h) / bh)
    ox = (width - bw * s) / 2.0 - minx * s
    oy = status_h + ((height - status_h) - bh * s) / 2.0 - miny * s

    def t(v: float) -> int:
        return int(round(v))

    def fit_btn(b: Btn) -> Btn:
        return Btn(
            mask=b.mask,
            x=t(b.x * s + ox),
            y=t(b.y * s + oy),
            r=max(2, t(b.r * s)),
            square=b.square,
            label=b.label,
            dpad=b.dpad,
        )

    lv = layout.lever
    return Layout(
        move=[fit_btn(b) for b in layout.move],
        cluster=[fit_btn(b) for b in layout.cluster],
        lever=Lever(
            x=t(lv.x * s + ox),
            y=t(lv.y * s + oy),
            ring=max(2, t(lv.ring * s)),
            knob=max(1, t(lv.knob * s)),
        ),
        show_lever=layout.show_lever,
    )
GROUP_MOVE = "move"
GROUP_CLUSTER = "cluster"
GROUP_LEVER = "lever"
GROUP_STATUS = "status"      # 状态栏文字 / 电量 / 无线图标
LEGACY_STATUS_KEY = "*"       # 上一版把状态栏位置存成一个全局值，读档时靠它兼容

# 状态栏元素的包围盒（固件 3x5 字形 × FONT_SCALE 2 → 每字符 8px 宽、10px 高）
STATUS_TEXT_SAMPLE = "SOCD:UP DP:DIG MODE:XIN"
STATUS_TEXT_W = len(STATUS_TEXT_SAMPLE) * 8       # 184
STATUS_TEXT_H = 10
STATUS_BATT_W, STATUS_BATT_H = 18, 10
STATUS_WIFI_R = 6


def status_extent(key: str) -> tuple[int, int]:
    """元素占的宽高；wifi 的 (x,y) 是圆心，这里按 2r 算。"""
    if key == STATUS_TEXT:
        return STATUS_TEXT_W, STATUS_TEXT_H
    if key == STATUS_BATT:
        return STATUS_BATT_W, STATUS_BATT_H
    return STATUS_WIFI_R * 2, STATUS_WIFI_R * 2


def clamp_status(sp: "StatusPos", key: str, width: int, height: int) -> bool:
    """把元素整体夹进屏幕（不是只夹锚点）。返回是否改动过。"""
    x, y = sp.get(key)
    if key == STATUS_WIFI:
        nx = max(STATUS_WIFI_R, min(width - STATUS_WIFI_R, x))
        ny = max(STATUS_WIFI_R, min(height - STATUS_WIFI_R, y))
    else:
        bw, bh = status_extent(key)
        nx = max(0, min(max(0, width - bw), x))
        ny = max(0, min(max(0, height - bh), y))
    if (nx, ny) != (x, y):
        sp.set(key, nx, ny)
        return True
    return False

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


def find_free_spot(layout: Layout, width: int = 240, height: int = 135) -> tuple[int, int]:
    """在右侧区域找一个不与现有按键重叠的默认放置点。

    width/height 限定搜索范围（Lite 用 128x64）。"""
    occupied = (
        [(b.x, b.y) for b in layout.move]
        + [(b.x, b.y) for b in layout.cluster]
    )
    ys = [y for y in (height - 30, height - 55, height - 80) if y > 12]
    xs = [x for x in (width // 2 - 40, width // 2 - 10, width - 90, width - 60, width - 30) if x > 6]
    for y in ys:
        for x in xs:
            if all((x - ox) ** 2 + (y - oy) ** 2 > 24 ** 2 for ox, oy in occupied):
                return x, y
    return xs[0] if xs else 8, ys[0] if ys else 16


# Lite 固件屏幕（configs/GPFusionLite/lite_display.h -> 0.96" 128x64），
# 顶部 8px 让给状态栏文字（模式/D-Pad/SOCD），按键只能画在它下面。
LITE_SCREEN: tuple[int, int] = (128, 64)
LITE_STATUS_H: int = 8


def sanitize_layout(
    layout: Layout,
    width: int,
    height: int,
    status_h: int = 0,
    min_r: int = 3,
    res: str = "",
) -> int:
    """把所有元素夹进目标屏幕，返回被修正的元素个数（原地修改）。

    固件是 1:1 按坐标画的：越界的按键在屏上直接消失、在画布上也抓不到，
    所以写头文件之前必须过一遍这里。
    """
    fixed = 0

    # 状态栏三个元素：夹当前分辨率这一条（其它分辨率的等切过去再夹）
    if res:
        sp = layout.status_by_res.get(str(res))
        if sp is not None:
            for key in STATUS_KEYS:
                if clamp_status(sp, key, int(width), int(height)):
                    fixed += 1

    # 半径上限要保证 [r+1, 屏边-r] 区间非空，同时不压到顶部状态栏，
    # 否则大半径会把圆心顶出屏（夹取区间反了）。
    r_max = max(
        min_r,
        min((width - 2) // 2, (height - 2) // 2, (height - 1 - status_h) // 2),
    )

    def clamp_btn(b: Btn) -> None:
        nonlocal fixed
        r = max(min_r, min(r_max, int(b.r)))
        x = max(r + 1, min(width - 1 - r, int(b.x)))
        y = max(max(r + 1, status_h + r), min(height - 1 - r, int(b.y)))
        if (r, x, y) != (int(b.r), int(b.x), int(b.y)):
            b.r, b.x, b.y = r, x, y
            fixed += 1

    for b in list(layout.move) + list(layout.cluster):
        clamp_btn(b)

    if layout.show_lever:
        lv = layout.lever
        knob = max(1, min(max(1, r_max - 1), int(lv.knob)))
        ring = max(knob + 1, min(max(knob + 1, r_max), int(lv.ring)))
        x = max(ring + 1, min(width - 1 - ring, int(lv.x)))
        y = max(max(ring + 1, status_h + ring), min(height - 1 - ring, int(lv.y)))
        if (knob, ring, x, y) != (int(lv.knob), int(lv.ring), int(lv.x), int(lv.y)):
            lv.knob, lv.ring, lv.x, lv.y = knob, ring, x, y
            fixed += 1
    return fixed
