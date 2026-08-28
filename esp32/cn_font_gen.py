#!/usr/bin/env python3
"""Generate esp32/cn_font.h: 16x16 1bpp Chinese glyphs for the GP-Fusion UI.

Uses the system Noto Sans CJK SC font. Add phrases below and re-run to grow
the subset; unknown characters simply render as blank.
"""
from PIL import Image, ImageDraw, ImageFont

FONT_PATH = "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc"
FONT_INDEX = 2          # Noto CJK TTC order: 0=JP 1=KR 2=SC 3=TC 4=HK
SIZE = 16
OUT = "/home/bit/GP2040-CE/esp32/cn_font.h"

# menu page titles + common UI words; deduplicated into the glyph set
PHRASES = [
    "设置", "电池", "灯光", "背景", "休眠",       # the 5 icon pages
    "菜单", "返回", "确定", "取消", "选择", "调整",
    "状态", "模式", "亮度", "颜色", "速度", "动画", "屏幕",
    "保存", "退出", "进入", "音量", "震动", "声音", "主题", "自定义",
    "电量", "输入", "手柄", "键位", "布局", "测试", "摇杆", "扳机",
    "已连接", "未连接", "百分比", "长按三秒", "增加", "减少", "开关",
    "版本", "关于", "上一页", "下一页", "主菜单", "待实现",
    "雪花", "弹跳", "管道", "吐司", "屏保时间", "关闭", "开启",
    "左右改值", "上下选择", "秒",
    "系统", "配置档", "保存设置", "恢复默认", "去抖延迟", "输入模式",
    "四向模式", "反向", "D-Pad模式", "A进入", "B返回",
    "是否立即保存", "左右选择", "A确认",
    "静态", "彩虹", "追逐", "主题", "自定义", "挂起关灯",
    "动画模式", "静态颜色", "亮度", "追逐速度", "彩虹速度",
    "流水",
    "电池供电", "USB连接",
    "背景透明度", "背光亮度", "水平翻转", "垂直翻转", "反色",
    "输入历史", "显示",
    "街机", "按键布局",
    "主题", "风格", "浅色",
    "品牌橙", "绯红", "翠绿", "紫罗兰", "青蓝",
    "复古", "扫描线", "暗角",
    "无线", "无线开关", "信道", "发射功率", "数据速率", "心跳频率",
    "重新配对", "省电", "标准", "高速", "远距", "低", "中", "最高",
    "断链",
]

chars = sorted(set("".join(PHRASES)))
codes = [ord(c) for c in chars]
assert all(c < 0x10000 for c in codes), "BMP only"

font = ImageFont.truetype(FONT_PATH, SIZE, index=FONT_INDEX)

glyphs = []
for ch in chars:
    img = Image.new("1", (SIZE, SIZE), 0)
    d = ImageDraw.Draw(img)
    bbox = d.textbbox((0, 0), ch, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (SIZE - w) // 2 - bbox[0]
    y = (SIZE - h) // 2 - bbox[1]
    d.text((x, y), ch, font=font, fill=1)
    data = []
    for row in range(SIZE):
        byte = 0
        for col in range(SIZE):
            if img.getpixel((col, row)):
                byte |= 0x80 >> (col & 7)
            if col % 8 == 7:
                data.append(byte)
                byte = 0
    glyphs.append(data)

with open(OUT, "w") as f:
    f.write("#pragma once\n#include <stdint.h>\n\n")
    f.write("#define CN_FONT_SIZE %d\n" % SIZE)
    f.write("#define CN_FONT_NUM %d\n" % len(chars))
    f.write("#define CN_FONT_GLYPH_BYTES %d\n\n" % (SIZE * SIZE // 8))
    f.write("// sorted BMP code points, one per glyph (binary-searchable)\n")
    f.write("const uint16_t CN_FONT_CODES[CN_FONT_NUM] = {\n")
    for i in range(0, len(codes), 16):
        f.write("  " + ", ".join("0x%04X" % c for c in codes[i:i + 16]) + ",\n")
    f.write("};\n\n")
    f.write("const uint8_t CN_FONT_GLYPHS[CN_FONT_NUM][CN_FONT_GLYPH_BYTES] = {\n")
    for g in glyphs:
        f.write("  {" + ",".join("0x%02X" % b for b in g) + "},\n")
    f.write("};\n")

print("wrote", OUT, "chars:", len(chars))
print("".join(chars))
