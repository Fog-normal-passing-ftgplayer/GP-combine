"""Lite 模式第 4 步：编译 Lite 固件并生成 UF2。"""
from __future__ import annotations

import os
import struct
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..jobs import JobRunner
from ..app_config import APP_VERSION
from ..wizard_state import WizardState
from .lite_source_page import lite_source_ready


def bin_to_uf2(bin_path: Path, uf2_path: Path, addr: int = 0x10000000) -> None:
    """把 RP2040 固件 .bin 转成 UF2（与 pico-sdk elf2uf2 格式一致）。"""
    data = bin_path.read_bytes()
    num = (len(data) + 255) // 256
    with open(uf2_path, "wb") as f:
        for i in range(num):
            chunk = data[i * 256:(i + 1) * 256]
            chunk = chunk.ljust(256, b"\x00")
            hdr = struct.pack(
                "<IIIIIIII",
                0x0A324655, 0x9E5D5157, 0x00002000,
                addr + i * 256, 256, i, num, 0xE48BFF56,
            )
            f.write(hdr + chunk + b"\x00" * (476 - 256) + struct.pack("<I", 0x0AB16F30))


class LiteUf2Page(QWidget):
    finished_build = Signal(bool)

    def __init__(self, state: WizardState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._runner: JobRunner | None = None
        self._busy = False
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 12)
        title = QLabel("Lite 版本 · 第 4 步：生成 UF2")
        title.setObjectName("StepTitle")
        root.addWidget(title)
        hint = QLabel(
            "用 cmake + make 编译 Lite 固件，产出可直接拖进 Pico 的 UF2。"
            "首次编译需要几分钟。"
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        root.addWidget(hint)
        root.addSpacing(8)

        info = QGroupBox("构建信息")
        info_l = QVBoxLayout(info)
        self.src_label = QLabel("源码目录：-")
        self.out_label = QLabel("输出：-")
        info_l.addWidget(self.src_label)
        info_l.addWidget(self.out_label)
        root.addWidget(info)

        row = QHBoxLayout()
        self.web_check = QCheckBox("包含网页配置（需要 Node/npm）")
        self.web_check.setChecked(True)
        row.addWidget(self.web_check)
        row.addStretch(1)
        root.addLayout(row)

        row = QHBoxLayout()
        self.start_btn = QPushButton("开始生成 UF2")
        self.start_btn.setObjectName("Primary")
        self.start_btn.clicked.connect(self.start)
        row.addWidget(self.start_btn)
        self.open_btn = QPushButton("打开输出目录")
        self.open_btn.clicked.connect(self.open_out)
        row.addWidget(self.open_btn)
        row.addStretch(1)
        root.addLayout(row)

        self.bar = QProgressBar()
        self.bar.setVisible(False)
        root.addWidget(self.bar)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        root.addWidget(self.log, 1)

    def on_shown(self) -> None:
        src = self.state.lite_source_dir
        if lite_source_ready(src):
            self.src_label.setText("源码目录：%s" % src)
            self.out_label.setText("输出：%s/build_lite/*.uf2" % src)
        else:
            self.src_label.setText("源码目录：-（请先完成第 1 步）")
            self.out_label.setText("输出：-")

    def start(self) -> None:
        if self._busy:
            return
        src = self.state.lite_source_dir
        if not lite_source_ready(src):
            self._log("请先在第 1 步选择有效的 Lite 源码文件夹")
            return
        self._busy = True
        self.bar.setVisible(True)
        self.bar.setRange(0, 0)
        self.start_btn.setEnabled(False)
        self._log("开始编译 Lite 固件…")

        self._build_dir = Path(src) / "build_lite"
        self._build_dir.mkdir(parents=True, exist_ok=True)
        self._pico_sdk = self.state.pico_sdk_dir or os.environ.get(
            "PICO_SDK_PATH", "/home/bit/pico/pico-sdk"
        )
        self._src = Path(src)

        # 清掉旧 UF2，保证构建后固定文件名就是本次的新固件
        for old in self._build_dir.glob("*.uf2"):
            try:
                old.unlink()
                self._log("已清理旧输出：%s" % old.name)
            except Exception:  # noqa: BLE001
                pass

        self._log("配置助手 v%s" % APP_VERSION)
        self._run_build(include_web=self.web_check.isChecked(), full_rebuild=True)

    def _run_build(self, include_web: bool, full_rebuild: bool = False) -> None:
        cmake_flags = [
            "-DPICO_SDK_PATH=%s" % self._pico_sdk,
            "-DGP2040_BOARDCONFIG=GPFusionLite",
        ]
        if not include_web:
            cmake_flags.append("-DSKIP_WEBBUILD=TRUE")
        cmds = [
            ["cmake"] + cmake_flags + [str(self._src)],
        ]
        if full_rebuild:
            cmds.append(["make", "clean"])
        cmds.append(["make", "-j4"])

        def run_next(failed: bool = False) -> None:
            if not cmds:
                if failed:
                    # make 失败：网页配置开启时自动降级重试，否则明确报错
                    if include_web:
                        self._log("⚠ 含网页配置编译失败，自动改为不含网页配置重试…")
                        self._run_build(include_web=False, full_rebuild=False)
                    else:
                        self._finish_fail("编译失败，未生成 UF2（请查看上方日志）")
                    return
                self._check_output()
                return
            cmd = cmds.pop(0)
            self._log("$ %s" % " ".join(cmd))
            runner = JobRunner()
            self._runner = runner
            runner.line_ready.connect(self._log)
            runner.finished.connect(lambda code: run_next(failed=(code != 0)))
            runner.start(cmd, cwd=self._build_dir)

        run_next()

    def _check_output(self) -> None:
        fixed = self._build_dir / "GP-Combine_0.1.0_GPFusionLite.uf2"
        uf2 = fixed if fixed.is_file() else next(self._build_dir.glob("*.uf2"), None)
        if uf2 is None or not uf2.is_file():
            # picotool 缺失时固件不会自动生成 UF2：用本次的 .bin 自己转
            bins = sorted(
                self._build_dir.glob("*.bin"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if bins:
                self._log("未找到 UF2，自动用 %s 生成…" % bins[0].name)
                try:
                    bin_to_uf2(bins[0], fixed)
                    uf2 = fixed
                except Exception as exc:  # noqa: BLE001
                    self._finish_fail("UF2 转换失败：%s" % exc)
                    return
        self._busy = False
        self.bar.setVisible(False)
        self.start_btn.setEnabled(True)
        if uf2 is not None and uf2.is_file():
            self._log("✔ 生成成功：%s" % uf2)
            self.finished_build.emit(True)
        else:
            self._finish_fail("make 成功但未找到 UF2 文件")

    def _finish_fail(self, msg: str) -> None:
        self._busy = False
        self.bar.setVisible(False)
        self.start_btn.setEnabled(True)
        self._log("✘ %s" % msg)
        self.finished_build.emit(False)

        run_next()

    def open_out(self) -> None:
        src = self.state.lite_source_dir
        if lite_source_ready(src):
            path = Path(src) / "build_lite"
            path.mkdir(parents=True, exist_ok=True)
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl

            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _log(self, line: str) -> None:
        self.log.appendPlainText(line)

    def reload_state(self) -> None:
        self.on_shown()
