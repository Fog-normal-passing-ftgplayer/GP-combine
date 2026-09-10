"""步骤：GIF 动画导入压缩（方案三：RLE 压缩 + 运行时解码）。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..app_config import local_gif_header, local_wallpaper_gfr, screen_dims
from ..gif_convert import generate_gif_header, generate_gif_gfr
from ..jobs import JobRunner
from ..wallpaper_fs import build_fs_image, flash_fs_cmd
from ..wizard_state import WizardState


class GifPage(QWidget):
    changed = Signal()

    MODES = [("cover", "裁切填满"), ("stretch", "拉伸填满"), ("fit", "等比居中")]

    def __init__(self, state: WizardState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._build_ui()
        self._load_previous()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 12)
        left = QVBoxLayout()
        title = QLabel("GIF 动画")
        title.setObjectName("StepTitle")
        left.addWidget(title)
        hint = QLabel("选择 GIF 动画，自动缩放成屏幕分辨率并做行程压缩，"
                      "生成固件内的 gif_user.h。作为屏保选择「GIF」播放；"
                      "若在「背景 / 壁纸」页选了「动态壁纸」，它将成为主界面动态背景（屏保禁用）。")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        left.addWidget(hint)
        left.addSpacing(8)

        row = QHBoxLayout()
        self.pick_btn = QPushButton("选择 GIF…")
        self.pick_btn.clicked.connect(self.pick_gif)
        row.addWidget(self.pick_btn)
        row.addWidget(QLabel("缩放"))
        self.mode_combo = QComboBox()
        for key, name in self.MODES:
            self.mode_combo.addItem(name, key)
        self.mode_combo.currentIndexChanged.connect(self._on_change)
        row.addWidget(self.mode_combo)
        row.addWidget(QLabel("调色板"))
        self.palette_combo = QComboBox()
        self.palette_combo.addItem("16 色（更小）", 16)
        self.palette_combo.addItem("32 色（画质更好）", 32)
        self.palette_combo.currentIndexChanged.connect(self._on_change)
        row.addWidget(self.palette_combo)
        left.addLayout(row)

        self.info = QLabel("未选择 GIF")
        self.info.setObjectName("Muted")
        self.info.setWordWrap(True)
        left.addWidget(self.info)

        self.gen_btn = QPushButton("生成并写入固件")
        self.gen_btn.setObjectName("Primary")
        self.gen_btn.clicked.connect(self.generate_now)
        left.addWidget(self.gen_btn)

        self.fs_btn = QPushButton("写入设备壁纸（LittleFS）")
        self.fs_btn.clicked.connect(self.flash_wallpaper_fs)
        left.addWidget(self.fs_btn)

        self.status = QLabel("")
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)
        left.addWidget(self.status)
        left.addStretch(1)
        root.addLayout(left, 2)

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(240 * 3, 135 * 3)
        self.preview.setStyleSheet(
            "background: #0D1117; border: 1px solid #232C3C; border-radius: 8px;"
        )
        root.addWidget(self.preview, 3)

    def _load_previous(self) -> None:
        if self.state.gif_src and Path(self.state.gif_src).is_file():
            self.info.setText("已选择：%s" % Path(self.state.gif_src).name)
            self._update_preview()

    def reload_state(self) -> None:
        self.info.setText("未选择 GIF")
        for i, (key, _name) in enumerate(self.MODES):
            if key == self.state.gif_mode:
                self.mode_combo.setCurrentIndex(i)
                break
        pi = self.palette_combo.findData(int(self.state.gif_palette))
        if pi >= 0:
            self.palette_combo.setCurrentIndex(pi)
        self._load_previous()
        if not self.state.gif_src or not Path(self.state.gif_src).is_file():
            self.preview.setPixmap(QPixmap())
        self.status.setText("")

    def pick_gif(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 GIF 动画", str(Path.home()), "GIF (*.gif)"
        )
        if not path:
            return
        self.state.gif_src = path
        self.state.save()
        self.info.setText("已选择：%s" % Path(path).name)
        self._update_preview()
        self.generate_now()

    def _on_change(self) -> None:
        self.state.gif_mode = self.MODES[self.mode_combo.currentIndex()][0]
        self.state.gif_palette = int(self.palette_combo.currentData())
        self.state.save()
        self._update_preview()
        self.generate_now()

    def _update_preview(self) -> None:
        if not self.state.gif_src or not Path(self.state.gif_src).is_file():
            self.preview.setPixmap(QPixmap())
            return
        try:
            im = Image.open(self.state.gif_src)
            im.seek(0)
            w, h = screen_dims(self.state.screen_res)
            im2 = im.convert("RGB").resize((w * 3, h * 3), Image.LANCZOS)
            qim = QImage(im2.tobytes("raw", "RGB"), im2.width, im2.height,
                         im2.width * 3, QImage.Format.Format_RGB888)
            self.preview.setPixmap(QPixmap.fromImage(qim))
        except Exception:
            self.preview.clear()

    def generate_now(self) -> None:
        if not self.state.gif_src or not Path(self.state.gif_src).is_file():
            self.status.setText("请先选择 GIF")
            self.status.setStyleSheet("color: #FFB454;")
            return
        if not self.state.source_dir:
            self.status.setText("源码目录未就绪")
            self.status.setStyleSheet("color: #FFB454;")
            return
        try:
            res = self.state.screen_res
            hdr = local_gif_header(Path(self.state.source_dir), res)
            if self.state.bg_kind == "dynamic":
                # 动态壁纸：只写卡内 /wp/1.gfr，不内嵌进 app（GIF 会顶爆分区）
                gfr = local_wallpaper_gfr(Path(self.state.source_dir))
                gfr, gf, gb = generate_gif_gfr(
                    self.state.gif_src, gfr,
                    self.MODES[self.mode_combo.currentIndex()][0],
                    palette_size=int(self.palette_combo.currentData()),
                    size=screen_dims(res),
                )
                if hdr.exists():
                    hdr.unlink()      # 移除旧的内嵌 GIF，省 app 空间
                    msg_extra = "（已移除内嵌 gif_user.h）"
                else:
                    msg_extra = ""
                msg = ("✔ 卡内壁纸 %s（%d 帧，%d KB）\n"
                       "动态壁纸模式不再内嵌 GIF%s；用「整机重刷」写入设备生效。"
                       % (gfr, gf, gb // 1024, msg_extra))
            else:
                out, frames, data_bytes = generate_gif_header(
                    self.state.gif_src,
                    hdr,
                    self.MODES[self.mode_combo.currentIndex()][0],
                    palette_size=int(self.palette_combo.currentData()),
                    size=screen_dims(res),
                )
                msg = "✔ 已写入 %s（%d 帧，压缩后 %d KB，作为 GIF 屏保）" % (
                    out, frames, data_bytes // 1024)
            self.status.setText(msg)
            self.status.setStyleSheet("color: #64E0A0;")
            self.changed.emit()
        except Exception as exc:  # noqa: BLE001
            self.status.setText("生成失败：%s" % exc)
            self.status.setStyleSheet("color: #FF7B72;")

    def flash_wallpaper_fs(self) -> None:
        """把 /wp/1.gfr 写入设备 LittleFS（仅 170x320，会清空板内配置）。"""
        if not self.state.source_dir:
            self.status.setText("源码目录未就绪")
            self.status.setStyleSheet("color: #FFB454;")
            return
        if not self.state.port:
            self.status.setText("未检测到 ESP32-S3 串口")
            self.status.setStyleSheet("color: #FFB454;")
            return
        gfr = local_wallpaper_gfr(Path(self.state.source_dir))
        if not gfr.is_file():
            self.generate_now()
        if not gfr.is_file():
            self.status.setText("卡内壁纸文件不存在，请先生成")
            self.status.setStyleSheet("color: #FF7B72;")
            return
        img = Path(self.state.source_dir) / "data" / "wp" / "littlefs.bin"
        ok, msg = build_fs_image(gfr.parent.parent, img)   # data/ 作为根，内含 wp/
        if not ok:
            self.status.setText(msg)
            self.status.setStyleSheet("color: #FF7B72;")
            return
        cmd = flash_fs_cmd(self.state.port, img)
        if cmd is None:
            self.status.setText("找不到 esptool，无法写入设备")
            self.status.setStyleSheet("color: #FF7B72;")
            return
        self.status.setText("%s\n正在写入设备（会清空板内配置）…" % msg)
        self.status.setStyleSheet("color: #50C8FF;")
        runner = JobRunner()
        self._fs_runner = runner
        runner.line_ready.connect(self._on_flash_log)
        runner.finished.connect(self._on_flash_done)
        runner.start(cmd)

    def _on_flash_log(self, line: str) -> None:
        self.status.setText(self.status.text().split("\n")[0] + "\n" + line.strip())

    def _on_flash_done(self, code: int) -> None:
        if code == 0:
            self.status.setText("✔ 壁纸文件已写入设备，断电重启后生效")
            self.status.setStyleSheet("color: #64E0A0;")
        else:
            self.status.setText("写入失败（退出码 %d）" % code)
            self.status.setStyleSheet("color: #FF7B72;")
