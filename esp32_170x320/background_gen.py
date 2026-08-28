#!/usr/bin/env python3
"""Generate esp32/background.h from a PNG for the GP-Fusion ESP32 UI.

Resizes the source image to the landscape content resolution (240x135),
blends it with the menu background color at a low opacity, and emits an
RGB565 array for direct memcpy into the framebuffer.
"""
import sys
from PIL import Image

SRC = "/home/bit/GP2040-CE/background/987292.png"
OUT = "/home/bit/GP2040-CE/esp32/background.h"
W, H = 240, 135
ALPHAS = (0.25, 0.40, 0.55, 0.70, 0.85)   # one variant per opacity level
BG = (21, 27, 39)     # COL_BG in the ESP32 sketch


def rgb565(r, g, b):
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


im = Image.open(SRC).convert("RGB").resize((W, H), Image.LANCZOS)
pixels = list(im.getdata())
variants = []
for alpha in ALPHAS:
    data = []
    for r, g, b in pixels:
        r2 = int(r * alpha + BG[0] * (1 - alpha))
        g2 = int(g * alpha + BG[1] * (1 - alpha))
        b2 = int(b * alpha + BG[2] * (1 - alpha))
        data.append(rgb565(r2, g2, b2))
    variants.append(data)

with open(OUT, "w") as f:
    f.write("#pragma once\n")
    f.write("#include <stdint.h>\n")
    f.write("\n// %dx%d background, opacity variants over RGB(%d,%d,%d)\n"
            % (W, H, *BG))
    for idx, alpha in enumerate(ALPHAS):
        data = variants[idx]
        f.write("// variant %d: image opacity %.2f\n" % (idx, alpha))
        f.write("const uint16_t BACKGROUND_IMG_%d[%d] PROGMEM = {\n" % (idx, W * H))
        for i in range(0, len(data), 16):
            f.write("  " + ", ".join("0x%04X" % v for v in data[i:i + 16]) + ",\n")
        f.write("};\n\n")
    f.write("#define BACKGROUND_LEVELS %d\n" % len(ALPHAS))
    f.write("const uint16_t *const BACKGROUND_IMG[BACKGROUND_LEVELS] PROGMEM = {\n")
    for idx in range(len(ALPHAS)):
        f.write("  BACKGROUND_IMG_%d,\n" % idx)
    f.write("};\n")

print("wrote", OUT, "variants:", len(ALPHAS), "entries:", len(variants[0]))
