"""懒人版界面：一屏搞定「选东西 → 一键刷」。

刻意只保留小白要用的东西：分辨率、背景/壁纸、按键布局、小游戏 ROM、几个按钮。
高级选项（自定义布局、Lite、网页配置）请用完整版配置助手。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from . import APP_TITLE
from .bundle_env import Env, refresh_cli_version, refresh_core_list
from .pipeline import (
    Options,
    StepError,
    compile_firmware,
    flash_prebuilt,
    full_reflash,
    upload_firmware,
    write_appearance,
    write_fs,
    write_nes,
)

MODES = [("cover", "裁切填满"), ("stretch", "拉伸"), ("fit", "等比留边")]


class Task(QThread):
    """在后台线程跑一个流程函数，日志逐行回传。"""

    line = Signal(str)
    done = Signal(bool, str)

    def __init__(self, fn: Callable[[Callable[[str], None]], None], title: str) -> None:
        super().__init__()
        self._fn = fn
        self._title = title

    def run(self) -> None:  # noqa: D102
        try:
            self._fn(self.line.emit)
            self.done.emit(True, "%s 完成" % self._title)
        except StepError as exc:
            self.line.emit("✘ %s" % exc)
            self.done.emit(False, str(exc))
        except Exception as exc:  # noqa: BLE001
            self.line.emit("✘ 意外错误：%r" % exc)
            self.done.emit(False, "意外错误：%r" % exc)


class Window(QWidget):
    def __init__(self, env: Env) -> None:
        super().__init__()
        self.env = env
        self.task: Task | None = None
        self.setWindowTitle("%s · %s" % (APP_TITLE, "离线包" if env.portable else "开发模式"))
        self.resize(880, 720)
        self._build()
        self._load_state()
        self._refresh_env()

    # ------------------------------------------------------------ 界面搭建

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.addWidget(self._env_bar())
        root.addWidget(self._appearance_box())
        root.addWidget(self._actions_box())
        root.addWidget(self._log_box(), 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        root.addWidget(self.progress)

    def _env_bar(self) -> QWidget:
        box = QGroupBox("环境")
        lay = QHBoxLayout(box)
        self.env_label = QLabel("探测中…")
        self.env_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.env_label, 1)
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(160)
        lay.addWidget(QLabel("串口"))
        lay.addWidget(self.port_combo)
        rbtn = QPushButton("刷新")
        rbtn.clicked.connect(self._refresh_env)
        lay.addWidget(rbtn)
        return box

    def _appearance_box(self) -> QWidget:
        box = QGroupBox("想要什么")
        form = QFormLayout(box)

        row_res = QHBoxLayout()
        self.rb_240 = QRadioButton("240x135（小屏）")
        self.rb_320 = QRadioButton("170x320（竖屏大屏）")
        self.rb_240.setChecked(True)
        row_res.addWidget(self.rb_240)
        row_res.addWidget(self.rb_320)
        row_res.addStretch(1)
        form.addRow("屏幕", self._wrap(row_res))

        self.layout_combo = QComboBox()
        for label in ("街机（摇杆）", "HITBOX", "WASD", "自定义（用源码里那份）"):
            self.layout_combo.addItem(label)
        form.addRow("按键布局", self.layout_combo)

        self.rb_static = QRadioButton("静态背景图")
        self.rb_dynamic = QRadioButton("动态壁纸（GIF）")
        self.rb_static.setChecked(True)
        self.bg_edit = QLineEdit()
        self.bg_edit.setPlaceholderText("选一张图片（会自动缩放到屏幕分辨率）")
        self.bg_pick = QPushButton("选择…")
        self.bg_pick.clicked.connect(lambda: self._pick_file(self.bg_edit, "图片", "Images (*.png *.jpg *.jpeg *.bmp *.webp)"))
        self.bg_mode = self._mode_combo()
        self.bg_kind_row = QHBoxLayout()
        self.bg_kind_row.addWidget(self.rb_static)
        self.bg_kind_row.addWidget(self.rb_dynamic)
        self.bg_kind_row.addStretch(1)
        form.addRow("背景", self._wrap(self.bg_kind_row))
        form.addRow("", self._with_button(self.bg_edit, self.bg_pick))
        form.addRow("", self._labelled("缩放方式", self.bg_mode))

        self.gif_edit = QLineEdit()
        self.gif_edit.setPlaceholderText("选一个 GIF（转成卡内 /wp/1.gfr，最多 60 帧）")
        self.gif_pick = QPushButton("选择…")
        self.gif_pick.clicked.connect(lambda: self._pick_file(self.gif_edit, "GIF", "GIF (*.gif)"))
        self.gif_mode = self._mode_combo()
        form.addRow("GIF", self._with_button(self.gif_edit, self.gif_pick))
        form.addRow("", self._labelled("缩放方式", self.gif_mode))

        self.nes_scale = QComboBox()
        self.nes_scale.addItem("拉伸铺满", 0)
        self.nes_scale.addItem("等比居中", 1)
        self.rom_edit = QLineEdit()
        self.rom_edit.setPlaceholderText("放 .nes 的文件夹（仅 170x320 可用）")
        self.rom_pick = QPushButton("选择…")
        self.rom_pick.clicked.connect(lambda: self._pick_dir(self.rom_edit))
        form.addRow("小游戏", self._with_button(self.rom_edit, self.rom_pick))
        form.addRow("", self._labelled("画面", self.nes_scale))
        return box

    def _actions_box(self) -> QWidget:
        box = QGroupBox("干活")
        lay = QHBoxLayout(box)
        self.btn_all = QPushButton("⚡ 一键编译并刷入")
        self.btn_all.clicked.connect(lambda: self._run_build(upload=True, full=False))
        self.btn_compile = QPushButton("只编译")
        self.btn_compile.clicked.connect(lambda: self._run_build(upload=False, full=False))
        self.btn_fs = QPushButton("写入卡内文件")
        self.btn_fs.setToolTip("把动态壁纸 / ROM 写进设备卡内（会清空板内卡上数据）")
        self.btn_fs.clicked.connect(self._run_fs)
        self.btn_full = QPushButton("整机重刷")
        self.btn_full.setToolTip("擦除 + bootloader/分区表/app/卡内文件，全量恢复")
        self.btn_full.clicked.connect(lambda: self._run_build(upload=True, full=True))
        self.btn_pre = QPushButton("刷预编译固件")
        self.btn_pre.setToolTip("直接用懒人包里的固件，不编译")
        self.btn_pre.clicked.connect(self._run_prebuilt)
        for b in (self.btn_all, self.btn_compile, self.btn_fs, self.btn_full, self.btn_pre):
            lay.addWidget(b)
        return box

    def _log_box(self) -> QWidget:
        box = QGroupBox("日志")
        lay = QVBoxLayout(box)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(4000)
        lay.addWidget(self.log)
        return box

    # ------------------------------------------------------------ 小工具

    @staticmethod
    def _wrap(lay) -> QWidget:
        w = QWidget()
        w.setLayout(lay)
        return w

    def _with_button(self, edit: QLineEdit, btn: QPushButton) -> QWidget:
        lay = QHBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(edit, 1)
        lay.addWidget(btn)
        return self._wrap(lay)

    def _labelled(self, text: str, widget: QWidget) -> QWidget:
        lay = QHBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QLabel(text))
        lay.addWidget(widget)
        lay.addStretch(1)
        return self._wrap(lay)

    def _mode_combo(self) -> QComboBox:
        c = QComboBox()
        for key, label in MODES:
            c.addItem(label, key)
        return c

    def _pick_file(self, target: QLineEdit, what: str, filt: str) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择%s" % what, "", filt)
        if path:
            target.setText(path)
            self._save_state()

    def _pick_dir(self, target: QLineEdit) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if path:
            target.setText(path)
            self._save_state()

    # ------------------------------------------------------------ 状态

    def _state_path(self) -> Path:
        base = self.env.work_dir or self.env.root
        base.mkdir(parents=True, exist_ok=True)
        return base / "dumb_state.json"

    def _save_state(self) -> None:
        data = {
            "res": self.options().res,
            "layout": self.layout_combo.currentIndex(),
            "bg_kind": self.options().bg_kind,
            "bg_path": self.bg_edit.text(),
            "bg_mode": self.bg_mode.currentData(),
            "gif_path": self.gif_edit.text(),
            "gif_mode": self.gif_mode.currentData(),
            "nes_scale": self.nes_scale.currentData(),
            "rom_dir": self.rom_edit.text(),
            "port": self.port_combo.currentText(),
        }
        try:
            self._state_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _load_state(self) -> None:
        p = self._state_path()
        if not p.is_file():
            return
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        (self.rb_320 if d.get("res") == "170x320" else self.rb_240).setChecked(True)
        self.layout_combo.setCurrentIndex(int(d.get("layout", 1)) % self.layout_combo.count())
        (self.rb_dynamic if d.get("bg_kind") == "dynamic" else self.rb_static).setChecked(True)
        self.bg_edit.setText(d.get("bg_path", ""))
        self.gif_edit.setText(d.get("gif_path", ""))
        self.rom_edit.setText(d.get("rom_dir", ""))
        for combo, key in ((self.bg_mode, "bg_mode"), (self.gif_mode, "gif_mode"),
                           (self.nes_scale, "nes_scale")):
            idx = combo.findData(d.get(key))
            if idx >= 0:
                combo.setCurrentIndex(idx)

    def options(self) -> Options:
        return Options(
            res="170x320" if self.rb_320.isChecked() else "240x135",
            layout=self.layout_combo.currentIndex(),
            bg_kind="dynamic" if self.rb_dynamic.isChecked() else "static",
            bg_path=self.bg_edit.text().strip(),
            bg_mode=str(self.bg_mode.currentData()),
            gif_path=self.gif_edit.text().strip(),
            gif_mode=str(self.gif_mode.currentData()),
            nes_scale=int(self.nes_scale.currentData()),
            rom_dir=self.rom_edit.text().strip(),
            port=self.port_combo.currentText().strip(),
        )

    def _refresh_env(self) -> None:
        refresh_cli_version(self.env)
        refresh_core_list(self.env)
        mode = "懒人包（离线）" if self.env.portable else "开发模式"
        marks = []
        marks.append(("arduino-cli ✔ %s" % (self.env.cli_version or "?")) if self.env.cli
                     else "arduino-cli ✘")
        marks.append("core ✔ %s" % ",".join(self.env.core_versions) if self.env.core_ok
                     else "core ✘")
        marks.append("源码 ✔" if self.env.sketch_240 and self.env.sketch_320 else "源码 ✘")
        self.env_label.setText("%s ｜ %s" % (mode, " ｜ ".join(marks)))

        self.port_combo.clear()
        try:
            from gpfusion_wizard.serial_detect import list_esp32_ports  # type: ignore

            for p in list_esp32_ports():
                self.port_combo.addItem(p)
        except Exception:  # noqa: BLE001
            pass
        ready = bool(self.env.cli and self.env.core_ok and self.env.sketch_240)
        for b in (self.btn_all, self.btn_compile, self.btn_fs, self.btn_full, self.btn_pre):
            b.setEnabled(ready)

    # ------------------------------------------------------------ 运行流程

    def _append(self, text: str) -> None:
        self.log.appendPlainText(text)

    def _start_task(self, fn: Callable[[Callable[[str], None]], None], title: str) -> None:
        if self.task and self.task.isRunning():
            return
        self._save_state()
        self.log.clear()
        self.progress.setVisible(True)
        for b in (self.btn_all, self.btn_compile, self.btn_fs, self.btn_full, self.btn_pre):
            b.setEnabled(False)
        self.task = Task(fn, title)
        self.task.line.connect(self._append)
        self.task.done.connect(self._on_done)
        self.task.start()

    def _on_done(self, ok: bool, msg: str) -> None:
        self.progress.setVisible(False)
        self._refresh_env()
        self._append("========== %s ==========" % msg)
        try:
            self.log.ensureCursorVisible()
        except Exception:  # noqa: BLE001
            pass

    def _run_build(self, upload: bool, full: bool) -> None:
        opt = self.options()

        def job(log: Callable[[str], None]) -> None:
            if full:
                full_reflash(self.env, opt, log)
                return
            write_appearance(self.env, opt, log)
            write_nes(self.env, opt, log)
            compile_firmware(self.env, opt, log)
            if upload:
                upload_firmware(self.env, opt, log)
            else:
                log("（只编译，未写入设备）")

        self._start_task(job, "整机重刷" if full else ("编译并刷入" if upload else "编译"))

    def _run_fs(self) -> None:
        opt = self.options()
        self._start_task(lambda log: write_fs(self.env, opt, log), "写入卡内文件")

    def _run_prebuilt(self) -> None:
        opt = self.options()

        def job(log: Callable[[str], None]) -> None:
            flash_prebuilt(self.env, opt.res, opt.port, log)

        self._start_task(job, "刷预编译固件")


def run(env: Env) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    win = Window(env)
    win.show()
    return app.exec() if hasattr(app, "exec") else app.exec_()
