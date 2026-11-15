#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成仿真器的巡演脚本（.tour）。

为什么要生成而不是手写：每步按键都要等动画（页滑动 280ms、列表动画 140ms），
手算时间点必错；而且 B 返回会把菜单游标重置到第 0 页，得随时跟踪当前位置。

导航事实（来自 esp32_170x320.ino）：
  * 长按 S2 >= 3000ms 从主页进菜单
  * VIEW_MENU: LEFT/RIGHT 翻页（menuMove），A 进子页
  * A 进子页时 subList = (该页分区数 > 1)：设置页(3 分区)先进分区列表，
    其余页单分区，直接进选项列表
  * subBack(): 从选项列表 B 回分区列表；从分区列表 B 回菜单且 **page 重置为 0**
  * page==6（小游戏）按 A -> nesScanRoms + VIEW_NES_LIST
"""
import sys

KEY = "right"

# 从主页进菜单并等待动画
START_MS = 3700          # setup 462ms + 开机动画 3200ms，期间固件忽略输入
S2_HOLD = 3200           # 固件阈值 3000ms，留 200ms 余量
SETTLE = 550             # 菜单出现后的稳定等待

TAP_HOLD = 130           # 一次点按按住的时长（<250ms，避免触发连发第二步）
PAGE_GAP = 480           # 页滑动动画 ANIM_MS=280
LIST_GAP = 380           # 列表动画 LIST_ANIM_MS=140 + 连发阈值 250
ENTER_GAP = 470          # 进子页后的绘制等待


class Tour:
    def __init__(self, start=START_MS):
        self.t = start
        self.lines = []

    def hold(self, dur, keys="none"):
        self.lines.append(f"hold {self.t} {self.t + dur} {keys}")
        self.t += dur
        return self

    def tap(self, keys, gap=LIST_GAP):
        self.hold(TAP_HOLD, keys)
        self.t += gap
        return self

    def wait(self, ms):
        self.t += ms
        return self

    def shot(self, name):
        self.lines.append(f"shot {name} {self.t}")
        return self

    def render(self):
        self.lines.append(f"end {self.t + 500}")
        return "\n".join(self.lines) + "\n"


def build(has_nes: bool):
    t = Tour()

    # --- 动态壁纸主页（进菜单之前截；壁纸 GIF 在这时已经在跑） ---
    t.wait(400)
    t.shot("home_wallpaper")

    # --- 长按 S2 进菜单 ---
    t.hold(S2_HOLD, "s2")
    t.wait(SETTLE)

    cur = 0   # 当前菜单游标所在页

    # ---------- 第 0 页：设置（3 个分区） ----------
    t.shot("page_01_setting")
    t.tap("a", ENTER_GAP)          # 进分区列表
    t.shot("setting_sections")
    t.tap("a", ENTER_GAP)          # 手柄
    t.shot("opt_handle")
    t.tap("b", LIST_GAP)           # 回分区列表
    t.tap("down")
    t.tap("a", ENTER_GAP)          # 显示
    t.shot("opt_display")
    t.tap("b", LIST_GAP)
    t.tap("down")
    t.tap("down")                  # 第三个分区：游标被重置过，要再按一次
    t.tap("a", ENTER_GAP)          # 系统
    t.shot("opt_system")
    t.tap("b", LIST_GAP)           # 回分区列表
    t.tap("b", SETTLE)             # 回菜单，page 重置为 0
    cur = 0

    # ---------- 其余页 ----------
    pages = [(1, "02_battery", "status"),
             (2, "03_led", "opts"),
             (3, "04_bg", "opts"),
             (4, "05_sleep", "opts"),
             (5, "06_wireless", "opts")]
    if has_nes:
        pages.append((6, "07_nes", "nes"))

    opt_name = {2: "opt_led", 3: "opt_bg", 4: "opt_sleep", 5: "opt_wireless"}

    for p, tag, kind in pages:
        # 从当前页移动到目标页
        if p > cur:
            for _ in range(p - cur):
                t.tap("right", PAGE_GAP)
        elif p < cur:
            for _ in range(cur - p):
                t.tap("left", PAGE_GAP)
        cur = p
        t.wait(150)
        t.shot(f"page_{tag}")

        if kind == "status":
            # 电池页没有分区，按 A 无反应，留在本页继续
            t.wait(200)
        elif kind == "nes":
            t.tap("a", ENTER_GAP + 150)   # 进 ROM 列表（需要扫目录，慢一点）
            t.shot("nes_list")
            t.wait(200)
        else:
            t.tap("a", ENTER_GAP)
            t.shot(opt_name[p])
            t.tap("b", SETTLE)            # 回菜单，page 重置为 0
            cur = 0
            t.wait(150)

    return t.render()


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "240"
    out = sys.argv[2] if len(sys.argv) > 2 else "-"
    text = build(has_nes=(which == "320"))
    if out == "-":
        sys.stdout.write(text)
    else:
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"写入 {out}（{len(text.splitlines())} 行）")
