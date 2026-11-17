#!/usr/bin/env python3
"""Generate esp32/icons.h: RGB565 arrays for the menu icons.

Reads every PNG in /home/bit/GP2040-CE/icons and emits a C header with one
const array per icon, named by the PNG basename (ASCII alnum only).
"""
from PIL import Image
import os, re

SRC_DIR = "/home/bit/GP2040-CE/icons"
OUT = "/home/bit/GP2040-CE/esp32/icons.h"


def rgb565(r, g, b):
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


entries = []
for name in sorted(os.listdir(SRC_DIR)):
    if not name.lower().endswith(".png"):
        continue
    im = Image.open(os.path.join(SRC_DIR, name)).convert("RGB")
    w, h = im.size
    data = [rgb565(*px) for px in im.getdata()]
    ident = re.sub(r"[^A-Za-z0-9]", "_", os.path.splitext(name)[0])
    entries.append((ident, w, h, data))

with open(OUT, "w") as f:
    f.write("#pragma once\n#include <stdint.h>\n\n")
    f.write("#define ICON_COUNT %d\n" % len(entries))
    for ident, w, h, data in entries:
        f.write("// %s (%dx%d)\n" % (ident, w, h))
        f.write("const uint16_t ICON_%s[%d] = {\n" % (ident, len(data)))
        for i in range(0, len(data), 16):
            f.write("  " + ", ".join("0x%04X" % v for v in data[i:i + 16]) + ",\n")
        f.write("};\n\n")
    f.write("typedef struct { const char* name; int w, h; const uint16_t* data; } IconDef;\n")
    f.write("const IconDef ICONS[ICON_COUNT] = {\n")
    for ident, w, h, data in entries:
        f.write('  {"%s", %d, %d, ICON_%s},\n' % (ident, w, h, ident))
    f.write("};\n")

print("wrote", OUT, "icons:", [e[0] for e in entries])
