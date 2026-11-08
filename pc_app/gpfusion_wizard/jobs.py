"""后台任务：子进程/下载的线程封装 + 进度解析（UI 通过信号接收）。"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tarfile
import threading
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Signal


class JobRunner(QObject):
    """在后台线程运行一条命令，逐行转发输出。"""

    line_ready = Signal(str)
    progress_changed = Signal(float)   # 0.0 ~ 1.0；解析器不识别时信号不发
    finished = Signal(int)             # 退出码

    def __init__(self) -> None:
        super().__init__()
        self._proc: subprocess.Popen | None = None

    def start(
        self,
        cmd: list[str],
        cwd: str | Path | None = None,
        parse_progress: Callable[[str], float | None] | None = None,
        env: dict | None = None,
    ) -> None:
        def worker() -> None:
            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(cwd) if cwd else None,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    encoding="utf-8",
                    errors="replace",
                )
                self._proc = proc
                assert proc.stdout is not None
                for line in proc.stdout:
                    line = line.rstrip("\r\n")
                    if line:
                        self.line_ready.emit(line)
                    if parse_progress:
                        p = parse_progress(line)
                        if p is not None:
                            self.progress_changed.emit(max(0.0, min(1.0, p)))
                code = proc.wait()
                self.finished.emit(code)
            except Exception as exc:  # noqa: BLE001
                self.line_ready.emit("错误: %s" % exc)
                self.finished.emit(-1)

        threading.Thread(target=worker, daemon=True).start()

    def terminate(self) -> None:
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass


class DownloadRunner(QObject):
    """后台下载文件（HTTP 流式），带真实进度。"""

    progress_changed = Signal(float)
    finished = Signal(int)
    error = Signal(str)

    def start(self, url: str, dest: str | Path, timeout: int = 120) -> None:
        def worker() -> None:
            tmp = str(dest) + ".part"
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": "GPFusion-Wizard/0.1"}
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp, \
                        open(tmp, "wb") as f:
                    total = int(resp.headers.get("Content-Length") or 0)
                    got = 0
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        got += len(chunk)
                        if total:
                            self.progress_changed.emit(got / total)
                os.replace(tmp, str(dest))
                self.finished.emit(0)
            except Exception as exc:  # noqa: BLE001
                self.error.emit(str(exc))
                self.finished.emit(-1)

        threading.Thread(target=worker, daemon=True).start()


def extract_archive(archive: str | Path, dest: str | Path) -> None:
    """解压 arduino-cli 发布包；包内只有 arduino-cli 一个可执行文件。"""
    archive = Path(archive)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(dest)
    else:
        with tarfile.open(archive, "r:gz") as tf:
            try:
                tf.extractall(dest, filter="data")
            except TypeError:  # Python < 3.12
                tf.extractall(dest)
    # 解压结果平铺：把 arduino-cli 可执行文件提到 dest 根目录
    exe = "arduino-cli.exe" if os.name == "nt" else "arduino-cli"
    found = list(dest.rglob(exe))
    if found and found[0].parent != dest:
        shutil.move(str(found[0]), str(dest / exe))
        archive.unlink(missing_ok=True)


# ---------- 进度解析 ----------

def git_clone_progress(line: str) -> float | None:
    m = re.search(r"Receiving objects:\s*(\d+)%", line)
    if m:
        return int(m.group(1)) / 100.0
    m = re.search(r"Resolving deltas:\s*(\d+)%", line)
    if m:
        return 0.94 + int(m.group(1)) / 100.0 * 0.06
    return None


def core_install_progress(_line: str) -> float | None:
    # arduino-cli 非交互输出没有百分比，返回 None 让界面走忙碌进度
    return None


def compile_progress(line: str) -> float | None:
    m = re.search(r"Compiling \S+\.(?:cpp|ino|c|h|S)\s*\.\.\.\s*(\d+)/(\d+)", line)
    if m:
        return int(m.group(1)) / max(1, int(m.group(2)))
    return None
