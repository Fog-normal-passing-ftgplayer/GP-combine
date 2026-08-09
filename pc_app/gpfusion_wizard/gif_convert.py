"""GIF -> 240x135 RGB565 帧 + RLE 压缩 -> gif_user.h（方案三：压缩存储+运行时解码）。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from .app_config import SCREEN_H, SCREEN_W


def _rgb565(r: int, g: int, b: int) -> int:
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def load_gif_frames(src: str | Path, mode: str = "cover", max_frames: int = 60):
    """读取 GIF，返回 [(PIL帧, 延时ms), ...]（已缩放到 240x135）。"""
    im = Image.open(src)
    frames: list[tuple[Image.Image, int]] = []
    try:
        while True:
            frame = im.convert("RGB")
            if mode == "stretch":
                frame = frame.resize((SCREEN_W, SCREEN_H), Image.LANCZOS)
            elif mode == "fit":
                frame.thumbnail((SCREEN_W, SCREEN_H), Image.LANCZOS)
                canvas = Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 0))
                canvas.paste(frame, ((SCREEN_W - frame.width) // 2,
                                     (SCREEN_H - frame.height) // 2))
                frame = canvas
            else:  # cover
                scale = max(SCREEN_W / frame.width, SCREEN_H / frame.height)
                f2 = frame.resize((round(frame.width * scale),
                                   round(frame.height * scale)), Image.LANCZOS)
                x = (f2.width - SCREEN_W) // 2
                y = (f2.height - SCREEN_H) // 2
                frame = f2.crop((x, y, x + SCREEN_W, y + SCREEN_H))
            delay = im.info.get("duration", 100) or 100
            frames.append((frame, delay))
            if len(frames) >= max_frames:
                break
            im.seek(im.tell() + 1)
    except EOFError:
        pass
    return frames


def rle_encode_rgb565(pixels: list[int]) -> list[int]:
    """行程编码：每段 [run-1, hi, lo]，run 最大 256。"""
    out: list[int] = []
    i = 0
    n = len(pixels)
    while i < n:
        v = pixels[i]
        run = 1
        while i + run < n and pixels[i + run] == v and run < 256:
            run += 1
        out.append(run - 1)
        out.append((v >> 8) & 0xFF)
        out.append(v & 0xFF)
        i += run
    return out


def generate_gif_header(
    src: str | Path,
    out_path: str | Path,
    mode: str = "cover",
    max_frames: int = 60,
) -> tuple[Path, int, int]:
    frames = load_gif_frames(src, mode, max_frames)
    assert frames, "GIF 没有可用的帧"
    delays = [d for _, d in frames]
    chunks: list[list[int]] = []
    for frame, _ in frames:
        px = list(frame.getdata())
        rgb = [_rgb565(*p) for p in px]
        chunks.append(rle_encode_rgb565(rgb))

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        f.write("#pragma once\n#include <stdint.h>\n\n")
        f.write("// 由 GP-Combine 配置助手生成（GIF 压缩：RLE），请勿手改。\n")
        f.write("#define GIF_USER_FRAMES %d\n" % len(frames))
        f.write("#define GIF_USER_WIDTH %d\n" % SCREEN_W)
        f.write("#define GIF_USER_HEIGHT %d\n" % SCREEN_H)
        f.write("static const uint16_t GIF_USER_DELAYS[%d] = {"
                % len(delays))
        f.write(",".join(str(d) for d in delays))
        f.write("};\n")
        f.write("static const uint32_t GIF_USER_OFFSETS[%d] = {" % len(chunks))
        off = 0
        offs = []
        for c in chunks:
            offs.append(off)
            off += len(c)
        f.write(",".join(str(o) for o in offs))
        f.write("};\n")
        total = sum(len(c) for c in chunks)
        f.write("#define GIF_USER_DATA_SIZE %d\n" % total)
        f.write("static const uint8_t GIF_USER_DATA[%d] = {\n" % total)
        pos = 0
        for c in chunks:
            for i in range(0, len(c), 24):
                f.write("  " + ",".join("0x%02X" % v for v in c[i:i + 24]) + ",\n")
            pos += len(c)
        f.write("};\n")
    return out, len(frames), sum(len(c) for c in chunks)
