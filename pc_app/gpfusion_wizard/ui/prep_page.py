"""步骤 0：连接 ESP32-S3 + 准备编译工具 + 准备固件源码。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..app_config import (
    DEFAULT_REPO_URL,
    default_cli_path,
    default_source_dir,
    arduino_cli_download_url,
)
from ..jobs import (
    DownloadRunner,
    JobRunner,
    core_install_progress,
    extract_archive,
)
from ..serial_detect import list_esp32_ports
from ..toolchain import (
    add_index_cmd,
    cli_version,
    config_init_cmd,
    core_install_cmd,
    core_installed,
    find_arduino_cli,
    git_available,
    git_clone_cmd,
    update_index_cmd,
)
from ..wizard_state import WizardState, source_ready


class PrepPage(QWidget):
    ready_changed = Signal()

    def __init__(self, state: WizardState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._cli_ok = False
        self._core_ok = False
        self._source_ok = False
        self._auto_started = False
        self._busy = False
        self._runner: JobRunner | DownloadRunner | None = None
        self._queue: list = []
        self._queue_final = None

        self._build_ui()
        self._refresh_all()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(2000)

    # ---------- UI ----------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 12)

        title = QLabel("第 1 步：连接与准备")
        title.setObjectName("StepTitle")
        root.addWidget(title)
        hint = QLabel(
            "插入 ESP32-S3 后会自动检测；检测到后开始下载编译工具并准备固件源码。"
            "首次准备需要几分钟，请保持网络畅通。"
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        root.addWidget(hint)
        root.addSpacing(10)

        # 设备
        dev = QGroupBox("ESP32-S3 设备")
        dev_l = QVBoxLayout(dev)
        row = QHBoxLayout()
        self.device_label = QLabel("未检测到设备")
        self.device_label.setObjectName("Muted")
        self.device_label.setStyleSheet("font-size: 15px; color: #FFB454;")
        refresh_btn = QPushButton("刷新检测")
        refresh_btn.clicked.connect(lambda: (self._refresh_port(), self._refresh_all()))
        row.addWidget(self.device_label)
        row.addStretch(1)
        row.addWidget(refresh_btn)
        dev_l.addLayout(row)
        root.addWidget(dev)

        # 编译工具
        tools = QGroupBox("编译工具（arduino-cli + ESP32 核心）")
        tools_l = QVBoxLayout(tools)

        cli_row = QHBoxLayout()
        cli_row.addWidget(QLabel("arduino-cli"))
        self.cli_status = QLabel("检查中…")
        self.cli_status.setObjectName("Muted")
        cli_row.addWidget(self.cli_status)
        cli_row.addStretch(1)
        self.cli_btn = QPushButton("安装")
        self.cli_btn.clicked.connect(self.manual_install_cli)
        cli_row.addWidget(self.cli_btn)
        tools_l.addLayout(cli_row)
        self.cli_bar = QProgressBar()
        self.cli_bar.setVisible(False)
        tools_l.addWidget(self.cli_bar)

        core_row = QHBoxLayout()
        core_row.addWidget(QLabel("ESP32 核心（esp32:esp32）"))
        self.core_status = QLabel("检查中…")
        self.core_status.setObjectName("Muted")
        core_row.addWidget(self.core_status)
        core_row.addStretch(1)
        self.core_btn = QPushButton("安装")
        self.core_btn.clicked.connect(self.manual_install_core)
        core_row.addWidget(self.core_btn)
        tools_l.addLayout(core_row)
        self.core_bar = QProgressBar()
        self.core_bar.setVisible(False)
        tools_l.addWidget(self.core_bar)
        root.addWidget(tools)

        # 固件源码
        src = QGroupBox("固件源码（GP-Fusion 仓库）")
        src_l = QVBoxLayout(src)
        url_row = QHBoxLayout()
        url_row.addWidget(QLabel("仓库地址"))
        self.url_edit = QLineEdit(DEFAULT_REPO_URL)
        self.url_edit.setPlaceholderText("请填写你 fork 的 GP-Fusion 仓库地址")
        url_row.addWidget(self.url_edit, 1)
        src_l.addLayout(url_row)

        self.src_status = QLabel("尚未选择源码目录")
        self.src_status.setObjectName("Muted")
        self.src_status.setWordWrap(True)
        src_l.addWidget(self.src_status)

        btn_row = QHBoxLayout()
        self.clone_btn = QPushButton("克隆仓库")
        self.clone_btn.clicked.connect(self.manual_clone)
        pick_btn = QPushButton("选择已有文件夹（跳过克隆）")
        pick_btn.clicked.connect(self.pick_local_folder)
        btn_row.addWidget(self.clone_btn)
        btn_row.addWidget(pick_btn)
        src_l.addLayout(btn_row)
        self.src_bar = QProgressBar()
        self.src_bar.setVisible(False)
        src_l.addWidget(self.src_bar)
        root.addWidget(src)

        # 日志
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(130)
        self.log.setPlaceholderText("准备日志…")
        root.addWidget(self.log, 1)

    # ---------- 状态 ----------

    def _log(self, line: str) -> None:
        self.log.appendPlainText(line)
        sb = self.log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _refresh_port(self) -> str:
        ports = list_esp32_ports()
        if ports:
            self.state.port = ports[0]
            self.device_label.setText("已检测：%s" % self.state.port)
            self.device_label.setStyleSheet("font-size: 15px; color: #64E0A0;")
        else:
            self.state.port = ""
            self.device_label.setText("未检测到设备（请插入 ESP32-S3）")
            self.device_label.setStyleSheet("font-size: 15px; color: #FFB454;")
        self.state.save()
        return self.state.port

    def _refresh_all(self) -> None:
        self._refresh_port()
        self._refresh_cli()
        self._refresh_core()
        self._refresh_source()

    def _refresh_cli(self) -> None:
        cli = find_arduino_cli()
        if cli:
            ver = cli_version(cli)
            self._cli_ok = True
            self.state.cli_path = str(cli)
            self.cli_status.setText("已就绪：%s" % (ver or cli.name))
            self.cli_status.setStyleSheet("color: #64E0A0;")
            self.cli_btn.setText("重新安装")
        else:
            self._cli_ok = False
            self.state.cli_path = ""
            self.cli_status.setText("未安装")
            self.cli_status.setStyleSheet("color: #FFB454;")
            self.cli_btn.setText("安装")
        self.state.save()
        self.ready_changed.emit()

    def _refresh_core(self) -> None:
        cli = find_arduino_cli()
        if cli and core_installed(cli):
            self._core_ok = True
            self.core_status.setText("已安装 esp32:esp32")
            self.core_status.setStyleSheet("color: #64E0A0;")
            self.core_btn.setText("重新安装")
        else:
            self._core_ok = False
            self.core_status.setText("未安装")
            self.core_status.setStyleSheet("color: #FFB454;")
            self.core_btn.setText("安装")
        self.ready_changed.emit()

    def _refresh_source(self) -> None:
        self._normalize_source_dir()
        if self.state.source_dir and source_ready(self.state.source_dir):
            self._source_ok = True
            ino = Path(self.state.source_dir, "esp32", "esp32.ino")
            try:
                supports_user_layout = "USER_LAYOUT" in ino.read_text(encoding="utf-8")
            except Exception:
                supports_user_layout = False
            if supports_user_layout:
                self.src_status.setText("源码已就绪：%s" % self.state.source_dir)
                self.src_status.setStyleSheet("color: #64E0A0;")
            else:
                self.src_status.setText(
                    "源码已就绪（注意：esp32.ino 较旧，不含 USER_LAYOUT，"
                    "按键布局自定义不会生效）：%s" % self.state.source_dir
                )
                self.src_status.setStyleSheet("color: #FFB454;")
        elif self.state.source_dir:
            self._source_ok = False
            self.src_status.setText(
                "所选目录缺少 esp32/esp32.ino：%s" % self.state.source_dir
            )
            self.src_status.setStyleSheet("color: #FF7B72;")
        else:
            self._source_ok = False
            self.src_status.setText("尚未选择源码目录")
            self.src_status.setStyleSheet("color: #8E9BAD;")
        self.state.save()
        self.ready_changed.emit()

    def _normalize_source_dir(self) -> None:
        """容错：如果用户选中了 esp32 固件目录本身，自动向上取仓库根目录。"""
        if not self.state.source_dir:
            return
        p = Path(self.state.source_dir)
        if (p / "esp32.ino").is_file() and not (p / "esp32" / "esp32.ino").is_file():
            self.state.source_dir = str(p.parent)

    def is_ready(self) -> bool:
        return bool(self.state.port) and self._cli_ok and self._core_ok and self._source_ok

    # ---------- 自动准备 ----------

    def _tick(self) -> None:
        if not self._refresh_port() or self._auto_started:
            return
        self._auto_started = True
        self._log("检测到 ESP32-S3（%s），开始自动准备…" % self.state.port)
        self._run_auto_prep()

    def _run_auto_prep(self) -> None:
        if self._busy:
            return
        if not self._cli_ok:
            self._install_cli()
        elif not self._core_ok:
            self._install_core()
        elif not self._source_ok:
            self._clone_repo()

    def _finish_step(self, label: str) -> None:
        self._busy = False
        self._refresh_all()
        self._log("✔ %s" % label)
        if self._queue:
            self._next_queue()
        else:
            self._run_auto_prep()

    def _fail_step(self, label: str, code: int) -> None:
        self._busy = False
        self._queue.clear()
        self._log("✘ %s（退出码 %d）" % (label, code))
        self._refresh_all()

    def _start_job(
        self,
        cmd: list[str],
        bar: QProgressBar,
        parser,
        label: str,
    ) -> None:
        self._busy = True
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setVisible(True)
        runner = JobRunner()
        self._runner = runner
        runner.line_ready.connect(self._log)

        def on_progress(p: float) -> None:
            bar.setValue(int(p * 100))

        runner.progress_changed.connect(on_progress)

        def on_done(code: int) -> None:
            bar.setVisible(False)
            if code == 0:
                self._finish_step(label)
            else:
                self._fail_step(label, code)

        runner.finished.connect(on_done)
        runner.start(cmd, parse_progress=parser)

    def _start_download(self, url: str, dest: Path, bar: QProgressBar, label: str) -> None:
        self._busy = True
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setVisible(True)
        dl = DownloadRunner()
        self._runner = dl
        dl.progress_changed.connect(lambda p: bar.setValue(int(p * 100)))
        dl.error.connect(self._log)

        def on_done(code: int) -> None:
            bar.setVisible(False)
            if code != 0:
                self._fail_step(label, -1)
                return
            self._log("下载完成，正在解压…")
            try:
                extract_archive(dest.with_suffix(dest.suffix + ".part"), dest.parent)
                self._log("解压完成：%s" % dest)
                self._finish_step(label)
            except Exception as exc:  # noqa: BLE001
                self._log("解压失败: %s" % exc)
                self._fail_step(label, -1)

        dl.finished.connect(on_done)
        dl.start(url, dest)

    # ---------- 手动触发 ----------

    def manual_install_cli(self) -> None:
        if not self._cli_ok:
            self._install_cli()
        else:
            self._install_cli(force=True)

    def _install_cli(self, force: bool = False) -> None:
        if self._busy:
            return
        if not force and find_arduino_cli():
            self._finish_step("arduino-cli 已就绪")
            return
        dest = default_cli_path()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dl_url = arduino_cli_download_url()
        self._log("开始下载 arduino-cli…")
        self._log(dl_url)
        self._start_download(dl_url, dest, self.cli_bar, "arduino-cli 安装")

    def manual_install_core(self) -> None:
        if not self._core_ok:
            self._install_core()
        else:
            self._install_core(force=True)

    def _install_core(self, force: bool = False) -> None:
        if self._busy:
            return
        cli = find_arduino_cli()
        if not cli:
            self._log("请先安装 arduino-cli")
            return
        if not force and core_installed(cli):
            self._finish_step("ESP32 核心已就绪")
            return
        self._log("安装 ESP32 核心 esp32:esp32（首次约 300MB，请耐心等待）…")
        self._queue = [
            (config_init_cmd(cli), self.core_bar, "初始化 arduino-cli 配置"),
            (add_index_cmd(cli), self.core_bar, "添加 ESP32 下载源"),
            (update_index_cmd(cli), self.core_bar, "更新板卡索引"),
            (core_install_cmd(cli), self.core_bar, "安装 ESP32 核心"),
        ]
        self._queue_final = lambda: self._finish_step("ESP32 核心安装完成")
        self._next_queue()

    def _next_queue(self) -> None:
        if not self._queue:
            if self._queue_final:
                self._queue_final()
            return
        cmd, bar, label = self._queue.pop(0)
        self._log("开始：%s" % label)
        self._start_job(cmd, bar, core_install_progress, label)

    def manual_clone(self) -> None:
        if self._busy:
            return
        if not git_available():
            self._log("未找到 git，请先安装 git，或使用「选择已有文件夹」跳过克隆。")
            return
        self._clone_repo()

    def _clone_repo(self) -> None:
        url = self.url_edit.text().strip()
        if not url:
            self._log("请先填写仓库地址")
            return
        dest = default_source_dir()
        if dest.exists() and any(dest.iterdir()):
            if source_ready(str(dest)):
                self.state.source_dir = str(dest)
                self._log("目标目录已存在且可用：%s" % dest)
                self._finish_step("源码已就绪")
                return
            self._log("目标目录 %s 已存在但缺少 esp32/esp32.ino" % dest)
            self._log("请用「选择已有文件夹」指定正确的 GP-Fusion 源码目录。")
            self._refresh_all()
            return
        self._log("开始克隆仓库：%s" % url)
        self._queue = [(git_clone_cmd(url, dest), self.src_bar, "克隆仓库")]
        self._queue_final = self._after_clone
        self._next_queue()

    def _after_clone(self) -> None:
        dest = default_source_dir()
        if source_ready(str(dest)):
            self.state.source_dir = str(dest)
            self._log("✔ 仓库克隆完成，源码位于：%s" % dest)
            self._finish_step("源码准备完成")
        else:
            self.state.source_dir = ""
            self._log(
                "克隆完成，但仓库中没有 esp32/esp32.ino——"
                "请确认填写的是包含 esp32 固件目录的 GP-Fusion 仓库地址。"
            )
            self._finish_step("克隆完成（目录不完整）")

    def pick_local_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择 GP-Fusion 源码文件夹")
        if not folder:
            return
        p = Path(folder)
        # 容错：直接选中了 esp32 固件目录本身时，自动向上取仓库根目录
        if (p / "esp32.ino").is_file() and not (p / "esp32" / "esp32.ino").is_file():
            p = p.parent
        self.state.source_dir = str(p)
        self.url_edit.setText(str(p))
        self._refresh_source()
