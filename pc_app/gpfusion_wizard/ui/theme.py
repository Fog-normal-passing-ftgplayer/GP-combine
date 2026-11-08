"""全局深色样式。"""

STYLE = """
* { font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif; }
QMainWindow, QWidget#Root {
  background: #151B27;
  color: #D7DEEB;
  font-size: 14px;
}
QWidget#Sidebar {
  background: #10151F;
  border-right: 1px solid #232C3C;
}
QLabel#AppTitle {
  color: #FFFFFF;
  font-size: 18px;
  font-weight: 600;
}
QLabel#AppSub {
  color: #7A879B;
  font-size: 12px;
}
QLabel#StepTitle {
  color: #FFFFFF;
  font-size: 17px;
  font-weight: 600;
}
QLabel#SectionTitle {
  color: #50C8FF;
  font-size: 14px;
  font-weight: 600;
}
QLabel#Hint, QLabel#Muted {
  color: #8E9BAD;
  font-size: 12px;
}
QLabel#Status {
  color: #64E0A0;
}
QLabel#Error {
  color: #FF7B72;
}
QListWidget#Steps {
  background: transparent;
  border: none;
  outline: none;
}
QListWidget#Steps::item {
  color: #8E9BAD;
  padding: 10px 14px;
  border-radius: 8px;
  margin: 2px 8px;
}
QListWidget#Steps::item:selected {
  background: #223047;
  color: #FFFFFF;
}
QListWidget#Steps::item:hover {
  background: #1B2434;
}
QPushButton {
  background: #223047;
  color: #D7DEEB;
  border: 1px solid #31415B;
  border-radius: 8px;
  padding: 8px 18px;
  min-height: 22px;
}
QPushButton:hover { background: #2A3C58; }
QPushButton:pressed { background: #1B2738; }
QPushButton:disabled { color: #5A6575; background: #1A2230; border-color: #252F40; }
QPushButton#Primary {
  background: #1F6FEB;
  border-color: #1F6FEB;
  color: #FFFFFF;
  font-weight: 600;
}
QPushButton#Primary:hover { background: #2F7DF5; }
QPushButton#Primary:disabled { background: #1E3A5F; border-color: #1E3A5F; color: #7E93AB; }
QPushButton#Danger { background: #5B1F2E; border-color: #7A2C40; }
QPushButton#Ghost {
  background: transparent;
  border: none;
  color: #50C8FF;
}
QLineEdit, QComboBox, QSpinBox {
  background: #1A2230;
  border: 1px solid #31415B;
  border-radius: 6px;
  padding: 6px 8px;
  color: #D7DEEB;
  selection-background-color: #1F6FEB;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
  border-color: #1F6FEB;
}
QComboBox::drop-down { border: none; width: 22px; }
QComboBox::down-arrow {
  image: none;
  border-left: 5px solid transparent;
  border-right: 5px solid transparent;
  border-top: 6px solid #8E9BAD;
  margin-right: 8px;
}
QComboBox QAbstractItemView {
  background: #1A2230;
  border: 1px solid #31415B;
  selection-background-color: #1F6FEB;
}
QSpinBox::up-button, QSpinBox::down-button { width: 18px; background: #223047; }
QSlider::groove:horizontal {
  height: 5px;
  background: #31415B;
  border-radius: 2px;
}
QSlider::sub-page:horizontal { background: #1F6FEB; border-radius: 2px; }
QSlider::handle:horizontal {
  width: 16px;
  margin: -6px 0;
  border-radius: 8px;
  background: #50C8FF;
}
QProgressBar {
  background: #1A2230;
  border: 1px solid #31415B;
  border-radius: 6px;
  text-align: center;
  color: #D7DEEB;
  min-height: 14px;
  max-height: 18px;
}
QProgressBar::chunk {
  background: #1F6FEB;
  border-radius: 5px;
}
QPlainTextEdit, QTextEdit {
  background: #0D1117;
  color: #B9C4D4;
  border: 1px solid #232C3C;
  border-radius: 6px;
  font-family: Consolas, "Courier New", monospace;
  font-size: 12px;
}
QGroupBox {
  border: 1px solid #232C3C;
  border-radius: 10px;
  margin-top: 14px;
  padding-top: 8px;
  font-weight: 600;
}
QGroupBox::title {
  subcontrol-origin: margin;
  left: 12px;
  padding: 0 6px;
  color: #50C8FF;
}
QCheckBox { spacing: 8px; }
QCheckBox::indicator {
  width: 16px; height: 16px;
  border: 1px solid #31415B;
  border-radius: 4px;
  background: #1A2230;
}
QCheckBox::indicator:checked { background: #1F6FEB; border-color: #1F6FEB; }
QToolTip {
  background: #223047;
  color: #FFFFFF;
  border: 1px solid #31415B;
  padding: 4px;
}
"""
