"""配置备份：把向导全套设置导出为 JSON，或从 JSON 恢复并写回源码目录。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .app_config import (
    APP_NAME,
    APP_VERSION,
    local_background_header,
    local_defaults_header,
    local_gif_header,
    local_layout_header,
    local_pico_user_header,
    screen_dims,
)
from .defaults_header import write_defaults_header
from .gif_convert import generate_gif_header
from .imagegen import generate_background_header
from .layout_header import write_layout_header
from .pico_config import write_pico_user_header
from .wizard_state import WizardState, source_ready

BACKUP_VERSION = 1


def export_config(state: WizardState, out_path: str | Path) -> dict[str, Any]:
    """把当前向导状态导出为 JSON，返回写入的内容。"""
    payload: dict[str, Any] = {
        "app": APP_NAME,
        "app_version": APP_VERSION,
        "backup_version": BACKUP_VERSION,
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "config": state.to_dict(),
    }
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def import_config(
    state: WizardState, in_path: str | Path
) -> tuple[WizardState, list[str]]:
    """从 JSON 恢复配置。

    返回 (新状态, 提示信息列表)。新状态的端口/工具链沿用当前机器，
    source_dir 优先恢复备份里的路径（仍有效时），否则沿用当前值。
    恢复后立即把可生成的 pico_user.h / defaults.h / layout_user.h 写回源码目录；
    background.h / gif_user.h 依赖原始图片文件，文件还在则一并重新生成。
    """
    p = Path(in_path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("备份文件格式不正确")
    cfg = data.get("config")
    if not isinstance(cfg, dict):
        raise ValueError("备份文件里没有 config 字段")

    new_state = WizardState.from_dict(cfg)
    notes = ["已从 %s 读取配置" % p.name]

    # 机器相关字段：端口/工具链沿用当前，源码目录按备份恢复（失效则沿用当前）
    new_state.port = state.port
    new_state.cli_path = state.cli_path
    src = Path(new_state.source_dir) if new_state.source_dir else None
    if src is None or not source_ready(str(src), new_state.screen_res):
        new_state.source_dir = state.source_dir
        src = Path(new_state.source_dir) if new_state.source_dir else None
        if src is None:
            notes.append("备份未包含有效源码目录，源码目录沿用当前值")

    if src is not None:
        try:
            write_pico_user_header(
                local_pico_user_header(src),
                led_pin=new_state.led_pin,
                leds_per_button=new_state.leds_per_button,
            )
            write_defaults_header(new_state.default_layout, local_defaults_header(src))
            write_layout_header(
                new_state.layout, local_layout_header(src, new_state.screen_res)
            )
            notes.append("灯序 / 布局 / 默认布局已写回源码目录")
        except Exception as exc:  # noqa: BLE001
            notes.append("写回源码目录失败：%s" % exc)

        bg = new_state.background_src
        if bg and Path(bg).is_file():
            try:
                generate_background_header(
                    bg, local_background_header(src, new_state.screen_res),
                    new_state.background_mode, size=screen_dims(new_state.screen_res),
                )
                notes.append("背景图已重新生成")
            except Exception as exc:  # noqa: BLE001
                notes.append("背景图重新生成失败（保留旧文件）：%s" % exc)
        else:
            notes.append("备份里的背景图文件不存在，背景沿用当前固件内旧图")

        gif = new_state.gif_src
        if gif and Path(gif).is_file():
            try:
                generate_gif_header(
                    gif,
                    local_gif_header(src, new_state.screen_res),
                    new_state.gif_mode,
                    palette_size=new_state.gif_palette,
                    size=screen_dims(new_state.screen_res),
                )
                notes.append("GIF 已重新生成")
            except Exception as exc:  # noqa: BLE001
                notes.append("GIF 重新生成失败（保留旧文件）：%s" % exc)
        else:
            notes.append("备份里的 GIF 文件不存在，GIF 沿用当前固件内旧动画")
    else:
        notes.append("源码目录未就绪，导入后请先完成第 1 步再生成文件")

    return new_state, notes
