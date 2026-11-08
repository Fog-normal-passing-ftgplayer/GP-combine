#!/usr/bin/env python3
"""生成 RP2040 的 flash_nuke.uf2：把整片 flash 写成 0。

用途：板子固件/配置坏掉、又不方便进 BOOTSEL 手动恢复时，
先用它把 flash 清空（之后 bootrom 会自己回到 BOOTSEL 模式），再刷正式固件。

用法：python3 tools/flash_nuke/make_flash_nuke.py [--size 0x200000] [--out /tmp/flash_nuke.uf2]
"""

import argparse
import struct

RP2040_FAMILY = 0xE48BFF56
MAGIC0 = 0x0A324655
MAGIC1 = 0x9E5D5157
MAGIC_END = 0x0AB16F30
FLASH_BASE = 0x10000000


def build(size: int) -> bytes:
    payload = 256
    n_blocks = size // payload
    out = bytearray()
    for i in range(n_blocks):
        block = struct.pack(
            "<8I",
            MAGIC0,
            MAGIC1,
            0x00002000,          # familyID present
            FLASH_BASE + i * payload,
            payload,
            i,
            n_blocks,
            RP2040_FAMILY,
        )
        block += bytes(payload)
        block += bytes(512 - 32 - payload - 4)   # UF2 块固定 512 字节
        block += struct.pack("<I", MAGIC_END)
        out += block
    return bytes(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", default="0x200000")
    ap.add_argument("--out", default="/tmp/flash_nuke.uf2")
    args = ap.parse_args()
    size = int(args.size, 0)
    data = build(size)
    with open(args.out, "wb") as fh:
        fh.write(data)
    print(f"{args.out}: {len(data)} bytes, wipes 0x{size:X} flash from 0x{FLASH_BASE:08X}")
    assert len(data) % 512 == 0, "UF2 块必须是 512 字节"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
