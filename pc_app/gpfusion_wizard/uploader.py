"""编译并上传 ESP32-S3 固件的命令构造与进度解析。"""
from __future__ import annotations

from pathlib import Path

from .app_config import FQBN


def compile_cmd(cli: Path, sketch_dir: Path, build_dir: Path,
                fqbn: str = FQBN) -> list[str]:
    return [
        str(cli),
        "compile",
        "--fqbn",
        fqbn,
        "--build-path",
        str(build_dir),
        str(sketch_dir),
    ]


def prepare_build_dir(build_dir: Path) -> Path | None:
    """编译前删掉 core/core.a，避免用到被写坏的归档。

    arduino-cli 是逐个对象文件往 core/core.a 里追加成员
    （xtensa-esp32s3-elf-gcc-ar cr core.a <obj>）。如果同一个 build 目录被
    两处编译同时写，归档会交错损坏：成员缺失、成员内容错位，链接期报满屏
    undefined reference（连 core 自己的 Esp / HardwareSerial / Stream /
    Print 都找不到），看起来像源码问题，其实和源码无关。
    core.a 只是 .o 的归档，删掉后由 arduino-cli 重建：约 1 秒、不会重新编译。
    """
    archive = Path(build_dir) / "core" / "core.a"
    try:
        if archive.is_file():
            archive.unlink()
            return archive
    except OSError:
        pass
    return None


def upload_cmd(cli: Path, port: str, build_dir: Path,
               fqbn: str = FQBN) -> list[str]:
    return [
        str(cli),
        "upload",
        "-p",
        port,
        "--fqbn",
        fqbn,
        "--input-dir",
        str(build_dir),
    ]
