"""GIF -> 目标分辨率调色板索引 + 行程压缩 -> gif_user.h（方案三：压缩存储+运行时解码）。

v2 格式：全局调色板（默认 16 色）+ 每帧像素索引行程编码 [len][idx]，
比 RGB565 原值 RLE 通常小 2~4 倍。
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from .app_config import SCREEN_RESOLUTIONS


def _rgb565(r: int, g: int, b: int) -> int:
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def load_gif_frames(
    src: str | Path,
    mode: str = "cover",
    max_frames: int = 60,
    size: tuple[int, int] | None = None,
):
    """读取 GIF，返回 [(PIL帧, 延时ms), ...]（已缩放到目标分辨率）。"""
    w, h = size or SCREEN_RESOLUTIONS["240x135"]
    im = Image.open(src)
    frames: list[tuple[Image.Image, int]] = []
    try:
        while True:
            frame = im.convert("RGB")
            if mode == "stretch":
                frame = frame.resize((w, h), Image.LANCZOS)
            elif mode == "fit":
                frame.thumbnail((w, h), Image.LANCZOS)
                canvas = Image.new("RGB", (w, h), (0, 0, 0))
                canvas.paste(frame, ((w - frame.width) // 2,
                                     (h - frame.height) // 2))
                frame = canvas
            else:  # cover
                scale = max(w / frame.width, h / frame.height)
                f2 = frame.resize((round(frame.width * scale),
                                   round(frame.height * scale)), Image.LANCZOS)
                x = (f2.width - w) // 2
                y = (f2.height - h) // 2
                frame = f2.crop((x, y, x + w, y + h))
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


def rle_encode_indices(indices: list[int]) -> list[int]:
    """索引行程编码：每段 [len, idx]，len==0 表示 256。"""
    out: list[int] = []
    i = 0
    n = len(indices)
    while i < n:
        v = indices[i]
        run = 1
        while i + run < n and indices[i + run] == v and run < 256:
            run += 1
        out.append(run & 0xFF)      # 256 -> 0
        out.append(v & 0xFF)
        i += run
    return out


def generate_gif_header(
    src: str | Path,
    out_path: str | Path,
    mode: str = "cover",
    max_frames: int = 60,
    palette_size: int = 16,
    size: tuple[int, int] | None = None,
) -> tuple[Path, int, int]:
    w, h = size or SCREEN_RESOLUTIONS["240x135"]
    frames = load_gif_frames(src, mode, max_frames, size)
    assert frames, "GIF 没有可用的帧"
    delays = [d for _, d in frames]

    # 全局调色板：对首帧做中位切分量化，其余帧映射到同一调色板（不抖动）
    pal_img = frames[0][0].quantize(
        colors=palette_size, method=Image.MEDIANCUT, dither=Image.Dither.NONE)
    palette = pal_img.getpalette()[:palette_size * 3]
    rgb_pal = [_rgb565(palette[i * 3], palette[i * 3 + 1], palette[i * 3 + 2])
               for i in range(palette_size)]

    chunks: list[list[int]] = []
    for frame, _ in frames:
        qi = frame.quantize(colors=palette_size, palette=pal_img,
                            dither=Image.Dither.NONE)
        chunks.append(rle_encode_indices(list(qi.getdata())))

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        f.write("#pragma once\n#include <stdint.h>\n\n")
        f.write("// 由 GP-Combine 配置助手生成（GIF 压缩：RLE），请勿手改。\n")
        f.write("#define GIF_USER_VERSION 2\n")
        f.write("#define GIF_USER_FRAMES %d\n" % len(frames))
        f.write("#define GIF_USER_WIDTH %d\n" % w)
        f.write("#define GIF_USER_HEIGHT %d\n" % h)
        f.write("#define GIF_USER_PALETTE_SIZE %d\n" % palette_size)
        f.write("static const uint16_t GIF_USER_PALETTE[%d] = {"
                % palette_size)
        f.write(",".join("0x%04X" % v for v in rgb_pal))
        f.write("};\n")
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
