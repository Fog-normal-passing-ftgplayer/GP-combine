"""整机重刷：写入 bootloader + 分区表 + app（可选卡内壁纸文件）。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..app_config import (
    default_tool_dir,
    fqbn_for,
    local_sketch_dir,
    local_wallpaper_gfr,
)
from ..jobs import JobRunner
from ..uploader import compile_cmd
from ..wallpaper_fs import (
    erase_flash_cmd,
    full_flash_cmd,
    stage_fs_image,
)
from ..wizard_state import WizardState


class ReflashPage(QWidget):
    finished = Signal(bool)

    def __init__(self, state: WizardState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._runner: JobRunner | None = None
        self._stage = ""
        self._pending = None
        self._build_ui()
        self._refresh_info()

    # ---------- UI ----------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 12)
        title = QLabel("整机重刷")
        title.setObjectName("StepTitle")
        root.addWidget(title)
        hint = QLabel(
            "写入完整固件：bootloader + 分区表 + 应用（+ 卡内壁纸文件）。"
            "分区表变更、换板、刷废后都用这个。约 1 分钟。"
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        root.addWidget(hint)
        root.addSpacing(8)

        info = QGroupBox("目标")
        info_l = QVBoxLayout(info)
        self.res_label = QLabel("-")
        self.port_label = QLabel("-")
        self.src_label = QLabel("-")
        for w in (self.res_label, self.port_label, self.src_label):
            w.setObjectName("Muted")
            info_l.addWidget(w)
        root.addWidget(info)

        opt = QGroupBox("选项")
        opt_l = QVBoxLayout(opt)
        self.fs_check = QCheckBox("同时写入卡内文件（壁纸 /wp/1.gfr）")
        self.fs_check.setChecked(True)
        opt_l.addWidget(self.fs_check)
        self.erase_check = QCheckBox("先整片擦除 flash（会清掉所有配置，慢一些）")
        opt_l.addWidget(self.erase_check)
        root.addWidget(opt)

        row = QHBoxLayout()
        self.start_btn = QPushButton("开始整机重刷")
        self.start_btn.setObjectName("Primary")
        self.start_btn.clicked.connect(self.start)
        row.addWidget(self.start_btn)
        row.addStretch(1)
        root.addLayout(row)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("重刷日志…")
        root.addWidget(self.log, 1)

    # ---------- 状态 ----------

    def on_shown(self) -> None:
        self._refresh_info()

    def reload_state(self) -> None:
        self._refresh_info()

    def _refresh_info(self) -> None:
        res = self.state.screen_res
        self.res_label.setText("分辨率：%s（%s）" % (res, fqbn_for(res)))
        self.port_label.setText("端口：%s" % (self.state.port or "未检测到"))
        self.src_label.setText("源码目录：%s" % (self.state.source_dir or "-"))
        gfr = local_wallpaper_gfr(Path(self.state.source_dir)) if self.state.source_dir else None
        has = bool(gfr and gfr.is_file())
        self.fs_check.setEnabled(has)
        self.fs_check.setChecked(has)
        self.fs_check.setText(
            "同时写入卡内文件（%s）" % (gfr if has else "未生成 /wp/1.gfr，先在 GIF 页生成")
        )

    def _log(self, line: str) -> None:
        self.log.appendPlainText(line)
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    # ---------- 流程 ----------

    def start(self) -> None:
        st = self.state
        cli = Path(st.cli_path) if st.cli_path else None
        if not cli or not cli.is_file():
            self._log("错误：arduino-cli 未就绪（设备与源码页安装）")
            return
        if not st.source_dir or not st.port:
            self._log("错误：需要源码目录 + ESP32-S3 串口")
            return
        self.log.clear()
        res = st.screen_res
        self._sketch = local_sketch_dir(Path(st.source_dir), res)
        self._build = default_tool_dir() / (
            "build_esp32s3_170x320" if res == "170x320" else "build_esp32s3")
        self._fqbn = fqbn_for(res)
        self._log("目标：%s（%s）" % (res, self._fqbn))
        self._log("① 编译固件…")
        self.start_btn.setEnabled(False)
        self._stage = "compile"
        runner = JobRunner()
        self._runner = runner
        runner.line_ready.connect(self._log)
        runner.finished.connect(self._after_compile)
        runner.start(compile_cmd(cli, self._sketch, self._build, self._fqbn))

    def _after_compile(self, code: int) -> None:
        if code != 0:
            self._log("✘ 编译失败")
            self.start_btn.setEnabled(True)
            return
        self._log("✔ 编译完成，开始写入…")
        fs_img = None
        if self.fs_check.isChecked():
            gfr = local_wallpaper_gfr(Path(self.state.source_dir))
            if gfr.is_file():
                fs_img = Path(self.state.source_dir) / "data" / "wp" / "littlefs.bin"
                ok, msg = stage_fs_image([(gfr, "wp/1.gfr")], fs_img)
                self._log(("✔ " if ok else "✘ ") + msg)
                if not ok:
                    fs_img = None
        boot = self._build / (self._sketch.name + ".ino.bootloader.bin")
        part = self._build / (self._sketch.name + ".ino.partitions.bin")
        app0 = self._build / "boot_app0.bin"
        app = self._build / (self._sketch.name + ".ino.bin")
        for p in (boot, part, app0, app):
            if not p.is_file():
                self._log("✘ 缺少构建产物：%s" % p)
                self.start_btn.setEnabled(True)
                return
        port = self.state.port
        if self.erase_check.isChecked():
            cmd = erase_flash_cmd(port)
            if cmd:
                self._log("② 整片擦除…")
                self._stage = "erase"
                self._run_cmd(cmd)
                self._pending = ("write", boot, part, app0, app, fs_img)
                return
        self._do_write(boot, part, app0, app, fs_img)

    def _do_write(self, boot, part, app0, app, fs_img) -> None:
        cmd = full_flash_cmd(self.state.port, boot, part, app0, app, fs_img)
        if cmd is None:
            self._log("✘ 找不到 esptool")
            self.start_btn.setEnabled(True)
            return
        self._log("② 写入整机固件%s…" % ("（含卡内文件）" if fs_img else ""))
        self._stage = "write"
        self._run_cmd(cmd)

    def _run_cmd(self, cmd: list[str]) -> None:
        runner = JobRunner()
        self._runner = runner
        runner.line_ready.connect(self._log)
        runner.finished.connect(self._after_step)
        runner.start(cmd)

    def _after_step(self, code: int) -> None:
        if code != 0:
            self._log("✘ 步骤失败（退出码 %d）" % code)
            self.start_btn.setEnabled(True)
            self.finished.emit(False)
            return
        if getattr(self, "_pending", None):
            _kind, boot, part, app0, app, fs_img = self._pending
            self._pending = None
            self._do_write(boot, part, app0, app, fs_img)
            return
        self._log("✔ 整机重刷完成，拔插一次即可启动")
        self.start_btn.setEnabled(True)
        self.finished.emit(True)
