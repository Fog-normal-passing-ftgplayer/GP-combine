"""编译并上传 ESP32-S3 固件的命令构造与进度解析。"""
from __future__ import annotations

from pathlib import Path

from .app_config import FQBN


def compile_cmd(cli: Path, sketch_dir: Path, build_dir: Path) -> list[str]:
    return [
        str(cli),
        "compile",
        "--fqbn",
        FQBN,
        "--build-path",
        str(build_dir),
        str(sketch_dir),
    ]


def upload_cmd(cli: Path, port: str, build_dir: Path) -> list[str]:
    return [
        str(cli),
        "upload",
        "-p",
        port,
        "--fqbn",
        FQBN,
        "--input-dir",
        str(build_dir),
    ]
