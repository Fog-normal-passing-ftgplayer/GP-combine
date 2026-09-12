"""懒人版的一键流程：写头文件 → 编译 → 刷入（全程离线，只用包内工具）。

这里不重复实现转换逻辑，全部复用 pc_app（gpfusion_wizard）里已经调好的代码：
背景图 / GIF / 布局 / 卡内文件镜像 / 编译上传命令。
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .bundle_env import Env, patch_pc_app_paths, refresh_core_list

LogFn = Callable[[str], None]


class StepError(RuntimeError):
    """流程中可直接展示给用户的错误。"""


@dataclass
class Options:
    res: str = "240x135"          # 240x135 / 170x320
    layout: int = 1               # 0 街机 1 HITBOX 2 WASD 3 自定义
    bg_kind: str = "static"       # static=静态背景 dynamic=动态壁纸(GIF)
    bg_path: str = ""
    bg_mode: str = "cover"        # cover / stretch / fit
    gif_path: str = ""
    gif_mode: str = "cover"
    gif_palette: int = 16
    nes_scale: int = 0            # 0 拉伸铺满 1 等比居中
    rom_dir: str = ""
    port: str = ""
    erase: bool = False
    fs_files: list[str] = field(default_factory=list)   # 额外要写进卡内的文件


def _log_noop(_msg: str) -> None:
    pass


def run(cmd: list[str], log: LogFn = _log_noop, cwd: Path | None = None) -> int:
    log("$ " + " ".join(str(c) for c in cmd))
    proc = subprocess.Popen(
        [str(c) for c in cmd],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=str(cwd) if cwd else None,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        log(line.rstrip())
    return proc.wait()


def run_checked(cmd: list[str], log: LogFn, what: str) -> None:
    if run(cmd, log) != 0:
        raise StepError("%s失败" % what)


def require_ready(env: Env, res: str) -> Path:
    if not env.source_dir or not env.source_dir.is_dir():
        raise StepError("没有源码目录，懒人包可能不完整")
    sketch = env.sketch(res)
    if not sketch or not sketch.is_dir():
        raise StepError("缺少 %s 源码目录" % res)
    if not env.cli:
        raise StepError("找不到 arduino-cli")
    if not env.core_versions:          # 界面之外直接调用时补一次探测
        refresh_core_list(env)
    if not env.core_ok:
        raise StepError("包内没有 esp32 core，懒人包可能不完整")
    return sketch


# ---------------------------------------------------------------- 外观 / 布局


def write_appearance(env: Env, opt: Options, log: LogFn = _log_noop) -> None:
    """按选择写入 background.h / bg_wallpaper.h / gif_user.h / 卡内 .gfr。"""
    patch_pc_app_paths(env)
    from gpfusion_wizard.app_config import (  # type: ignore
        local_gif_header,
        local_wallpaper_gfr,
        local_wallpaper_header,
        screen_dims,
    )
    from gpfusion_wizard.imagegen import generate_background_header  # type: ignore

    src = Path(env.source_dir)
    bg_header = env.sketch(opt.res)
    if bg_header is None:
        raise StepError("源码目录未就绪")
    bg_header = bg_header / "background.h"
    marker = local_wallpaper_header(src, opt.res)
    gif_header = local_gif_header(src, opt.res)

    if opt.bg_kind == "dynamic":
        if not opt.gif_path or not Path(opt.gif_path).is_file():
            raise StepError("动态壁纸需要选择 GIF 文件")
        marker.write_text("#pragma once\n#define BG_WALLPAPER 1\n", encoding="utf-8")
        gfr = local_wallpaper_gfr(src)
        gfr.parent.mkdir(parents=True, exist_ok=True)
        from gpfusion_wizard.gif_convert import generate_gif_gfr  # type: ignore

        out, frames, size_b = generate_gif_gfr(
            opt.gif_path,
            gfr,
            opt.gif_mode,
            palette_size=int(opt.gif_palette),
            size=screen_dims(opt.res),
        )
        if gif_header.exists():
            gif_header.unlink()
        log("✔ 动态壁纸：%s（%d 帧，%d KB）" % (out, frames, size_b // 1024))
    else:
        if marker.exists():
            marker.unlink()
        if opt.bg_path and Path(opt.bg_path).is_file():
            out = generate_background_header(
                opt.bg_path, bg_header, opt.bg_mode, screen_dims(opt.res)
            )
            log("✔ 静态背景：%s（%s）" % (out, opt.bg_mode))
        else:
            log("· 未选背景图，保留源码自带的背景")

    from gpfusion_wizard.defaults_header import write_defaults_header  # type: ignore

    write_defaults_header(opt.layout, env.sketch(opt.res) / "defaults.h")  # type: ignore[operator]
    log("✔ 菜单默认布局：%s" % ("街机", "HITBOX", "WASD", "自定义")[opt.layout])


def write_nes(env: Env, opt: Options, log: LogFn = _log_noop) -> None:
    """小游戏：缩放模式 + ROM 复制到 data/nes（仅 170x320 生效）。"""
    if opt.res != "170x320":
        return
    sketch = env.sketch(opt.res)
    if sketch is None:
        return
    conf = sketch / "nes_conf.h"
    conf.write_text(
        "#pragma once\n// 由 GP-Combine 配置助手生成：NES 缩放模式\n"
        "#define NES_SCALE_MODE %d\n" % int(opt.nes_scale),
        encoding="utf-8",
    )
    log("✔ 小游戏缩放：%s" % ("等比居中" if opt.nes_scale else "拉伸铺满"))

    if opt.rom_dir and Path(opt.rom_dir).is_dir():
        dst = Path(env.source_dir) / "data" / "nes"
        dst.mkdir(parents=True, exist_ok=True)
        roms = sorted(Path(opt.rom_dir).glob("*.nes"))
        copied = 0
        for rom in roms:
            shutil.copy2(rom, dst / rom.name)
            copied += 1
        log("✔ 已导入 %d 个 ROM 到 data/nes/" % copied)


# ---------------------------------------------------------------- 编译 / 上传


def build_dir(env: Env, res: str) -> Path:
    return (env.work_dir or env.root) / ("build_%s" % res.replace("x", "_"))


def compile_firmware(env: Env, opt: Options, log: LogFn = _log_noop) -> Path:
    require_ready(env, opt.res)
    from gpfusion_wizard.app_config import fqbn_for  # type: ignore
    from gpfusion_wizard.uploader import compile_cmd  # type: ignore

    sketch = env.sketch(opt.res)
    out = build_dir(env, opt.res)
    out.mkdir(parents=True, exist_ok=True)
    cmd = compile_cmd(env.cli, sketch, out, fqbn_for(opt.res))  # type: ignore[arg-type]
    log("编译 %s（%s）…" % (opt.res, sketch.name))
    run_checked(cmd, log, "编译")
    log("✔ 编译完成：%s" % out)
    return out


def upload_firmware(env: Env, opt: Options, log: LogFn = _log_noop) -> None:
    from gpfusion_wizard.app_config import fqbn_for  # type: ignore
    from gpfusion_wizard.uploader import upload_cmd  # type: ignore

    if not opt.port:
        raise StepError("没有检测到串口，请插好板子并进入下载模式")
    out = build_dir(env, opt.res)
    cmd = upload_cmd(env.cli, opt.port, out, fqbn_for(opt.res))  # type: ignore[arg-type]
    log("写入 %s…" % opt.port)
    run_checked(cmd, log, "写入")
    log("✔ 已刷入设备")


# ------------------------------------------------------- 卡内文件 / 整机重刷


def stage_fs(env: Env, opt: Options, log: LogFn = _log_noop) -> Path | None:
    """把动态壁纸 / ROM / 用户附加文件打包成 littlefs 镜像。"""
    patch_pc_app_paths(env)
    from gpfusion_wizard.app_config import local_nes_dir, local_wallpaper_gfr  # type: ignore
    from gpfusion_wizard.wallpaper_fs import stage_fs_image  # type: ignore

    src = Path(env.source_dir)
    files: list[tuple[Path, str]] = []
    if opt.bg_kind == "dynamic":
        gfr = local_wallpaper_gfr(src)
        if gfr.is_file():
            files.append((gfr, "wp/1.gfr"))
    rom_dir = local_nes_dir(src)
    if rom_dir.is_dir():
        for rom in sorted(rom_dir.glob("*.nes")):
            files.append((rom, "nes/" + rom.name))
    for extra in opt.fs_files:
        p = Path(extra)
        if p.is_file():
            files.append((p, p.name))
    if not files:
        return None
    img = (env.work_dir or src) / "littlefs.bin"
    img.parent.mkdir(parents=True, exist_ok=True)
    ok, msg = stage_fs_image(files, img)
    log(("✔ " if ok else "✘ ") + msg)
    if not ok:
        raise StepError("卡内文件打包失败")
    log("  卡内文件：" + "、".join(inner for _s, inner in files))
    return img


def write_fs(env: Env, opt: Options, log: LogFn = _log_noop) -> None:
    patch_pc_app_paths(env)
    from gpfusion_wizard.wallpaper_fs import flash_fs_cmd  # type: ignore

    if not opt.port:
        raise StepError("没有检测到串口")
    img = stage_fs(env, opt, log)
    if img is None:
        raise StepError("没有要写入的卡内文件（先选动态壁纸或导入 ROM）")
    cmd = flash_fs_cmd(opt.port, img)
    if not cmd:
        raise StepError("包内缺少 esptool（应该在 arduino-data/packages/esp32/tools 下）")
    run_checked(cmd, log, "写入卡内文件")
    log("✔ 卡内文件已写入")


def full_reflash(env: Env, opt: Options, log: LogFn = _log_noop) -> None:
    """整机重刷：擦除（可选）+ bootloader/分区表/app（+ 卡内文件）。"""
    patch_pc_app_paths(env)
    from gpfusion_wizard.wallpaper_fs import (  # type: ignore
        erase_flash_cmd,
        full_flash_cmd,
    )

    if not opt.port:
        raise StepError("没有检测到串口")
    out = compile_firmware(env, opt, log)
    fs_img = stage_fs(env, opt, log)

    sketch_name = env.sketch(opt.res).name  # type: ignore[union-attr]
    boot = out / (sketch_name + ".ino.bootloader.bin")
    part = out / (sketch_name + ".ino.partitions.bin")
    app0 = out / "boot_app0.bin"
    app = out / (sketch_name + ".ino.bin")
    missing = [p.name for p in (boot, part, app0, app) if not p.is_file()]
    if missing:
        raise StepError("缺少构建产物：%s" % "、".join(missing))

    if opt.erase:
        cmd = erase_flash_cmd(opt.port)
        if cmd:
            log("整片擦除…")
            run_checked(cmd, log, "擦除")
    cmd = full_flash_cmd(opt.port, boot, part, app0, app, fs_img)
    if not cmd:
        raise StepError("包内缺少 esptool")
    log("写入整机固件%s…" % ("（含卡内文件）" if fs_img else ""))
    run_checked(cmd, log, "整机写入")
    log("✔ 整机重刷完成")


def flash_prebuilt(env: Env, res: str, port: str, log: LogFn = _log_noop) -> None:
    """刷包内预编译固件（firmware/esp32_<res>/）。"""
    patch_pc_app_paths(env)
    from gpfusion_wizard.wallpaper_fs import full_flash_cmd  # type: ignore

    base = (env.firmware_dir or env.root) / ("esp32_%s" % res.replace("x", "_"))
    app = base / "app.bin"
    boot = base / "bootloader.bin"
    part = base / "partitions.bin"
    app0 = base / "boot_app0.bin"
    fs_img = base / "littlefs.bin"
    if not app.is_file():
        raise StepError("预编译固件不存在：%s" % base)
    if not port:
        raise StepError("没有检测到串口")
    cmd = full_flash_cmd(
        port, boot, part, app0, app, fs_img if fs_img.is_file() else None
    )
    if not cmd:
        raise StepError("包内缺少 esptool")
    log("写入预编译固件 %s…" % base.name)
    run_checked(cmd, log, "刷入预编译固件")
    log("✔ 预编译固件已刷入")
