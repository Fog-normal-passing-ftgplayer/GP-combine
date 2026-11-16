"""全局深色样式（GP-Combine 品牌橙）。"""

ACCENT = "#FF7A00"
ACCENT_HOVER = "#FF8C1A"
ACCENT_SOFT = "#FFB273"
BG = "#0B0D12"
BG_HEADER = "#10141B"
BG_SIDEBAR = "#0E1116"
BG_CARD = "#141922"
BG_INPUT = "#11161E"
BORDER = "#242B36"
BORDER_STRONG = "#2C3442"
TEXT = "#E7EBF2"
MUTED = "#8B95A7"

STYLE = f"""
* {{
  font-family: "Noto Sans CJK SC", "Microsoft YaHei", "PingFang SC", sans-serif;
}}
QWidget#Root, QWidget#Content {{
  background: {BG};
  color: {TEXT};
  font-size: 14px;
}}
QWidget#Header {{
  background: {BG_HEADER};
  border-bottom: 1px solid #222833;
}}
QWidget#Sidebar {{
  background: {BG_SIDEBAR};
  border-right: 1px solid #222833;
}}
QWidget#Footer {{
  background: {BG_HEADER};
  border-top: 1px solid #222833;
}}
QStackedWidget {{ background: transparent; }}

QLabel {{
  color: {TEXT};
  background: transparent;
}}
QLabel#Logo {{
  background: {ACCENT};
  color: #FFFFFF;
  border-radius: 10px;
  font-size: 15px;
  font-weight: 700;
}}
QLabel#AppTitle {{
  color: #FFFFFF;
  font-size: 17px;
  font-weight: 700;
}}
QLabel#AppSub {{
  color: {MUTED};
  font-size: 12px;
}}
QLabel#VersionChip {{
  background: #1E242D;
  color: {ACCENT_SOFT};
  border: 1px solid {BORDER_STRONG};
  border-radius: 10px;
  padding: 3px 9px;
  font-size: 11px;
  font-weight: 600;
}}
QLabel#NavCaption {{
  color: #6F7A8C;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 1px;
  padding: 2px 6px;
}}
QLabel#SidebarFoot, QLabel#FooterHint {{
  color: #5F6A7C;
  font-size: 11px;
}}
QLabel#StatusText {{
  color: {MUTED};
  font-size: 12px;
}}
QLabel#StatusDot {{
  font-size: 13px;
}}
QLabel#StepTitle {{
  color: #FFFFFF;
  font-size: 20px;
  font-weight: 700;
}}
QLabel#SectionTitle {{
  color: {ACCENT_SOFT};
  font-size: 13px;
  font-weight: 600;
}}
QLabel#Hint, QLabel#Muted {{
  color: {MUTED};
  font-size: 12px;
}}
QLabel:disabled {{ color: #5F6A7C; }}
QCheckBox:disabled {{ color: #5F6A7C; }}
QComboBox:disabled, QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
  color: #5F6A7C;
  background: #0E1116;
  border-color: {BORDER};
}}
QLabel#Status {{ color: #3DDC97; }}
QLabel#Error {{ color: #FF7B72; }}

QListWidget#Steps {{
  background: transparent;
  border: none;
  outline: none;
}}
QListWidget#Steps::item {{
  color: #A7B0C0;
  padding: 9px 10px;
  border-radius: 9px;
  margin: 1px 2px;
  border-left: 3px solid transparent;
}}
QListWidget#Steps::item:selected {{
  background: #2A1E12;
  color: #FFD9B0;
  border-left: 3px solid {ACCENT};
}}
QListWidget#Steps::item:hover {{
  background: #1A202A;
}}

QPushButton {{
  background: #1A202A;
  color: #DDE3EC;
  border: 1px solid {BORDER_STRONG};
  border-radius: 8px;
  padding: 8px 16px;
  min-height: 20px;
}}
QPushButton:hover {{
  background: #222A36;
  border-color: #3A4454;
}}
QPushButton:pressed {{ background: #151A22; }}
QPushButton:disabled {{
  color: #5F6A7C;
  background: {BG_CARD};
  border-color: {BORDER};
}}
QPushButton#Primary {{
  background: {ACCENT};
  border-color: {ACCENT};
  color: #1A120A;
  font-weight: 700;
}}
QPushButton#Primary:hover {{
  background: {ACCENT_HOVER};
  border-color: {ACCENT_HOVER};
}}
QPushButton#Primary:pressed {{ background: #E56A00; }}
QPushButton#Primary:disabled {{
  background: #4A3520;
  border-color: #4A3520;
  color: #9A7A55;
}}
QPushButton#Ghost {{
  background: transparent;
  border: none;
  color: #AEB8C8;
  padding: 6px 10px;
}}
QPushButton#Ghost:hover {{
  background: #1A202A;
  color: #FFFFFF;
}}
QPushButton#Danger {{
  background: #3A1A1A;
  border-color: #5A2626;
  color: #FF9A9A;
}}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
  background: {BG_INPUT};
  border: 1px solid {BORDER_STRONG};
  border-radius: 7px;
  padding: 7px 9px;
  color: {TEXT};
  selection-background-color: {ACCENT};
  selection-color: #1A120A;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
  border-color: {ACCENT};
}}
QComboBox#ModeCombo {{
  background: #1A202A;
  border: 1px solid {BORDER_STRONG};
  border-radius: 8px;
  padding: 7px 12px;
  min-width: 104px;
}}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox::down-arrow {{
  image: none;
  border-left: 4px solid transparent;
  border-right: 4px solid transparent;
  border-top: 5px solid {MUTED};
  margin-right: 6px;
}}
QComboBox QAbstractItemView {{
  background: #151A22;
  border: 1px solid {BORDER_STRONG};
  selection-background-color: {ACCENT};
  selection-color: #1A120A;
  outline: none;
}}
QSpinBox::up-button, QSpinBox::down-button {{
  width: 18px;
  background: #1A202A;
  border: none;
}}

QSlider::groove:horizontal {{
  height: 5px;
  background: {BORDER_STRONG};
  border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
  background: {ACCENT};
  border-radius: 2px;
}}
QSlider::handle:horizontal {{
  width: 16px;
  margin: -6px 0;
  border-radius: 8px;
  background: {ACCENT_HOVER};
}}
QProgressBar {{
  background: {BG_INPUT};
  border: 1px solid {BORDER_STRONG};
  border-radius: 6px;
  text-align: center;
  color: {TEXT};
  min-height: 14px;
  max-height: 18px;
}}
QProgressBar::chunk {{
  background: {ACCENT};
  border-radius: 5px;
}}

QPlainTextEdit, QTextEdit {{
  background: #090C11;
  color: #B9C4D4;
  border: 1px solid {BORDER};
  border-radius: 8px;
  font-family: "JetBrains Mono", "Consolas", monospace;
  font-size: 12px;
}}

QGroupBox {{
  background: {BG_CARD};
  border: 1px solid {BORDER};
  border-radius: 12px;
  margin-top: 18px;
  padding: 16px 14px 12px;
  font-weight: 600;
}}
QGroupBox::title {{
  subcontrol-origin: margin;
  left: 14px;
  padding: 0 6px;
  color: {ACCENT_SOFT};
  background: {BG_CARD};
}}

QCheckBox {{ spacing: 8px; color: #DDE3EC; }}
QCheckBox::indicator {{
  width: 16px; height: 16px;
  border: 1px solid #3A4454;
  border-radius: 4px;
  background: {BG_INPUT};
}}
QCheckBox::indicator:checked {{
  background: {ACCENT};
  border-color: {ACCENT};
}}
QRadioButton {{ spacing: 8px; color: #DDE3EC; }}
QRadioButton::indicator {{
  width: 15px; height: 15px;
  border: 1px solid #3A4454;
  border-radius: 8px;
  background: {BG_INPUT};
}}
QRadioButton::indicator:checked {{
  background: {ACCENT};
  border-color: {ACCENT};
}}

QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

QScrollBar:vertical {{
  background: transparent;
  width: 10px;
  margin: 2px;
}}
QScrollBar::handle:vertical {{
  background: {BORDER_STRONG};
  border-radius: 5px;
  min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: #3A4454; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{
  background: transparent;
  height: 10px;
  margin: 2px;
}}
QScrollBar::handle:horizontal {{
  background: {BORDER_STRONG};
  border-radius: 5px;
  min-width: 30px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}

QTabWidget::pane {{
  border: 1px solid {BORDER};
  border-radius: 10px;
  background: #12161D;
  top: -1px;
}}
QTabBar::tab {{
  background: transparent;
  color: {MUTED};
  padding: 8px 14px;
  margin-right: 4px;
  border-radius: 8px;
}}
QTabBar::tab:selected {{ background: #1E242D; color: #FFFFFF; }}
QTabBar::tab:hover {{ color: #FFFFFF; }}

QTableWidget {{
  background: {BG_INPUT};
  border: 1px solid {BORDER};
  border-radius: 8px;
  gridline-color: {BORDER};
  selection-background-color: #2A1E12;
  selection-color: #FFD9B0;
}}
QHeaderView::section {{
  background: #151A22;
  color: {MUTED};
  border: none;
  padding: 6px;
}}

QMenu {{
  background: #151A22;
  border: 1px solid {BORDER_STRONG};
  padding: 6px;
}}
QMenu::item {{
  padding: 6px 18px;
  border-radius: 5px;
}}
QMenu::item:selected {{ background: {ACCENT}; color: #1A120A; }}

QToolTip {{
  background: #1E242D;
  color: #FFFFFF;
  border: 1px solid {BORDER_STRONG};
  padding: 5px;
}}

QDialog {{ background: {BG_HEADER}; color: {TEXT}; }}
"""
