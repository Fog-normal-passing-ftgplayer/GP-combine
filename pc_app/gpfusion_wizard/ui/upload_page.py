"""步骤 4：编译并上传固件到 ESP32-S3。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..app_config import (
    FQBN,
    default_tool_dir,
    fqbn_for,
    local_background_header,
    local_sketch_dir,
    local_sketch_ino,
    local_wallpaper_header,
    local_wallpaper_gfr,
)
from ..jobs import JobRunner, compile_progress
from ..uploader import compile_cmd, prepare_build_dir, upload_cmd
from ..wizard_state import WizardState


class UploadPage(QWidget):
    finished_upload = Signal(bool)

    def __init__(self, state: WizardState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._runner: JobRunner | None = None
        self._phase = "idle"   # idle | compile | upload | done | failed
        self._auto_started = False
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 12)

        title = QLabel("编译上传")
        title.setObjectName("StepTitle")
        root.addWidget(title)
        hint = QLabel("上传前请保持 ESP32-S3 通过 USB 连接。首次编译需要几分钟，请稍候。")
        hint.setObjectName("Hint")
        root.addWidget(hint)
        root.addSpacing(8)

        info = QGroupBox("上传信息")
        info_l = QVBoxLayout(info)
        self.port_label = QLabel("端口：-")
        self.src_label = QLabel("源码目录：-")
        self.board_label = QLabel("目标板：ESP32-S3（%s）" % FQBN)
        info_l.addWidget(self.port_label)
        info_l.addWidget(self.src_label)
        info_l.addWidget(self.board_label)
        root.addWidget(info)

        self.status_label = QLabel("准备就绪，点击「开始上传」")
        self.status_label.setObjectName("Muted")
        root.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        root.addWidget(self.progress)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("编译/上传日志…")
        root.addWidget(self.log, 1)

        btn_row = QHBoxLayout()
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.cancel)
        self.cancel_btn.setVisible(False)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addStretch(1)
        self.start_btn = QPushButton("开始上传")
        self.start_btn.setObjectName("Primary")
        self.start_btn.clicked.connect(self.start)
        btn_row.addWidget(self.start_btn)
        root.addLayout(btn_row)

    # ---------- 生命周期 ----------

    def on_shown(self) -> None:
        self.port_label.setText("端口：%s" % (self.state.port or "未检测到"))
        self.src_label.setText("源码目录：%s" % (self.state.source_dir or "-"))
        res = self.state.screen_res
        self.board_label.setText(
            "目标板：ESP32-S3（%s）%s" % (
                fqbn_for(res),
                "　16MB 自定义分区（app 3MB / LittleFS 12.94MB）"
                if res == "170x320" else "",
            )
        )
        if self._auto_started:
            return
        self._auto_started = True
        self.start()

    def _log(self, line: str) -> None:
        self.log.appendPlainText(line)
        sb = self.log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _set_status(self, text: str, color: str = "#8E9BAD") -> None:
        self.status_label.setText(text)
        self.status_label.setStyleSheet("color: %s;" % color)

    # ---------- 编译上传 ----------

    def start(self) -> None:
        if self._phase in ("compile", "upload"):
            return
        cli = Path(self.state.cli_path) if self.state.cli_path else None
        if not cli or not cli.is_file():
            self._set_status("arduino-cli 未就绪，请到「设备与源码」页安装", "#FF7B72")
            self._log("错误：找不到 arduino-cli")
            self.finished_upload.emit(False)
            return
        res = self.state.screen_res
        if not self.state.source_dir or not local_sketch_ino(
            Path(self.state.source_dir), res
        ).is_file():
            self._set_status("源码目录未就绪，请到「设备与源码」页设置", "#FF7B72")
            self.finished_upload.emit(False)
            return
        if self.state.bg_kind == "dynamic":
            wp_h = local_wallpaper_header(Path(self.state.source_dir), res)
            if not wp_h.is_file():
                self._set_status("动态壁纸未启用，请先在「背景 / 壁纸」页选择「动态壁纸」",
                                 "#FFB454")
                self.finished_upload.emit(False)
                return
            gfr = local_wallpaper_gfr(Path(self.state.source_dir))
            if not gfr.is_file():
                self._set_status(
                    "缺少卡内壁纸 data/wp/1.gfr，请先在「GIF 动画」页生成",
                    "#FFB454")
                self.finished_upload.emit(False)
                return
        else:
            bg_h = local_background_header(Path(self.state.source_dir), res)
            if not bg_h.is_file():
                self._set_status("缺少 background.h，请先在「背景 / 壁纸」页生成", "#FFB454")
                self._log("错误：%s 不存在" % bg_h)
                self.finished_upload.emit(False)
                return
        if not self.state.port:
            self._set_status("未插入 ESP32-S3，不写入固件，插入后再试", "#FFB454")
            self._log("未插入 ESP32-S3：不写入固件，插入后重试上传。")
            self.finished_upload.emit(False)
            return

        sketch_dir = local_sketch_dir(Path(self.state.source_dir), res)
        fqbn = fqbn_for(res)
        build_dir = default_tool_dir() / (
            "build_esp32s3_170x320" if res == "170x320" else "build_esp32s3")
        stale = prepare_build_dir(build_dir)
        self.log.clear()
        if stale:
            self._log("已清理旧 core.a（防归档损坏导致的满屏 undefined reference）")
        self._log("目标：N16R8（16MB flash + 8MB PSRAM），自定义分区 "
                  "app 3MB / LittleFS 12.94MB")
        self._log("提示：首次写入会重排分区表，板内 LittleFS 会被清空"
                  "（屏幕配置会自动从 Pico 镜像恢复）")
        self._set_status("正在编译固件…（首次约 2~5 分钟）", "#50C8FF")
        self.progress.setVisible(True)
        self.start_btn.setEnabled(False)
        self.cancel_btn.setVisible(True)
        self._phase = "compile"
        self._log("$ %s" % " ".join(compile_cmd(cli, sketch_dir, build_dir, fqbn)))
        runner = JobRunner()
        self._runner = runner
        runner.line_ready.connect(self._log)
        runner.finished.connect(self._on_compile_done)
        runner.start(
            compile_cmd(cli, sketch_dir, build_dir, fqbn),
            parse_progress=compile_progress,
        )

    def _on_compile_done(self, code: int) -> None:
        if code != 0:
            self._phase = "failed"
            self._set_status("编译失败，请查看上方日志", "#FF7B72")
            self.start_btn.setEnabled(True)
            self.cancel_btn.setVisible(False)
            self.progress.setVisible(False)
            self.finished_upload.emit(False)
            return
        self._log("✔ 编译成功，开始上传…")
        self._phase = "upload"
        self._set_status("正在上传到 ESP32-S3…", "#50C8FF")
        cli = Path(self.state.cli_path)
        res2 = self.state.screen_res
        fqbn2 = fqbn_for(res2)
        build_dir = default_tool_dir() / (
            "build_esp32s3_170x320" if res2 == "170x320" else "build_esp32s3")
        self._log("$ %s" % " ".join(upload_cmd(cli, self.state.port, build_dir, fqbn2)))
        runner = JobRunner()
        self._runner = runner
        runner.line_ready.connect(self._log)
        runner.finished.connect(self._on_upload_done)
        runner.start(upload_cmd(cli, self.state.port, build_dir, fqbn2))

    def _on_upload_done(self, code: int) -> None:
        self.progress.setVisible(False)
        self.cancel_btn.setVisible(False)
        self.start_btn.setEnabled(True)
        if code == 0:
            self._phase = "done"
            self._set_status("上传完成 🎉 固件已写入 ESP32-S3", "#64E0A0")
            self.finished_upload.emit(True)
        else:
            self._phase = "failed"
            text = self.log.toPlainText()
            if ("Serial data stream stopped" in text
                    or "Connecting" in text
                    or "Failed to connect" in text
                    or "No serial data received" in text):
                self._set_status(
                    "连接失败：按住 BOOT 键再点「开始上传」，"
                    "出现写入进度后松开 BOOT；并确认是数据线",
                    "#FFB454",
                )
                self._log("提示：若仍失败，先按住 BOOT 键，再点「开始上传」，"
                          "看到写入进度后再松开 BOOT。")
            else:
                self._set_status("上传失败，请检查端口后重试", "#FF7B72")
            self.finished_upload.emit(False)

    def cancel(self) -> None:
        if self._runner:
            self._runner.terminate()
        self._phase = "failed"
        self._set_status("已取消", "#FFB454")
        self.progress.setVisible(False)
        self.cancel_btn.setVisible(False)
        self.start_btn.setEnabled(True)
