"""Theme stylesheets and color definitions for Open-Canoe."""

DARK_THEME = """
QMainWindow, QDialog {
    background-color: #1e1e2e;
    color: #cdd6f4;
}
QMenuBar {
    background-color: #181825;
    color: #cdd6f4;
    border-bottom: 1px solid #313244;
}
QMenuBar::item:selected {
    background-color: #45475a;
}
QMenu {
    background-color: #1e1e2e;
    color: #cdd6f4;
    border: 1px solid #313244;
}
QMenu::item:selected {
    background-color: #45475a;
}
QToolBar {
    background-color: #181825;
    border-bottom: 1px solid #313244;
    spacing: 4px;
    padding: 2px;
}
QToolButton {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 4px 12px;
    margin: 2px;
}
QToolButton:hover {
    background-color: #45475a;
}
QToolButton:pressed {
    background-color: #585b70;
}
QToolButton:checked {
    background-color: #89b4fa;
    color: #1e1e2e;
}
QStatusBar {
    background-color: #181825;
    color: #a6adc8;
    border-top: 1px solid #313244;
}
QDockWidget {
    color: #cdd6f4;
}
QDockWidget::title {
    background-color: #181825;
    padding: 4px 8px;
    border-bottom: 1px solid #313244;
}
QGroupBox {
    color: #cdd6f4;
    border: 1px solid #313244;
    border-radius: 6px;
    margin-top: 8px;
    padding-top: 16px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}
QTableView, QTreeView {
    background-color: #1e1e2e;
    color: #cdd6f4;
    gridline-color: #313244;
    border: 1px solid #313244;
    selection-background-color: #45475a;
    alternate-background-color: #232336;
}
QTableView::item, QTreeView::item {
    padding: 3px 6px;
}
QHeaderView::section {
    background-color: #313244;
    color: #cdd6f4;
    padding: 4px 8px;
    border: 1px solid #45475a;
    font-weight: bold;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 4px 8px;
}
QLineEdit:focus, QSpinBox:focus {
    border-color: #89b4fa;
}
QComboBox::drop-down {
    border: none;
    padding-right: 6px;
}
QComboBox QAbstractItemView {
    background-color: #1e1e2e;
    color: #cdd6f4;
    selection-background-color: #45475a;
}
QPushButton {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 6px 16px;
}
QPushButton:hover {
    background-color: #45475a;
}
QPushButton:pressed {
    background-color: #585b70;
}
QPushButton:disabled {
    background-color: #2a2a3a;
    color: #6c7086;
}
QPushButton#primaryBtn {
    background-color: #89b4fa;
    color: #1e1e2e;
    border-color: #89b4fa;
    font-weight: bold;
}
QPushButton#primaryBtn:hover {
    background-color: #b4d0fb;
}
QPushButton#dangerBtn {
    background-color: #f38ba8;
    color: #1e1e2e;
    border-color: #f38ba8;
}
QCheckBox {
    color: #cdd6f4;
}
QLabel {
    color: #cdd6f4;
}
QProgressBar {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 4px;
    text-align: center;
    color: #cdd6f4;
}
QProgressBar::chunk {
    background-color: #89b4fa;
    border-radius: 3px;
}
QSplitter::handle {
    background-color: #45475a;
    margin: 1px;
}
QScrollBar:vertical {
    background-color: #1e1e2e;
    width: 10px;
    border: none;
}
QScrollBar::handle:vertical {
    background-color: #45475a;
    border-radius: 5px;
    min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QTabWidget::pane {
    border: 1px solid #313244;
    background-color: #1e1e2e;
}
QTabBar::tab {
    background-color: #313244;
    color: #cdd6f4;
    padding: 6px 16px;
    border: 1px solid #45475a;
    border-bottom: none;
}
QTabBar::tab:selected {
    background-color: #1e1e2e;
    border-bottom: 2px solid #89b4fa;
}
QToolTip {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
}
"""

LIGHT_THEME = """
QMainWindow, QDialog {
    background-color: #eff1f5;
    color: #4c4f69;
}
QMenuBar {
    background-color: #e6e9ef;
    color: #4c4f69;
    border-bottom: 1px solid #ccd0da;
}
QMenuBar::item:selected {
    background-color: #ccd0da;
}
QMenu {
    background-color: #eff1f5;
    color: #4c4f69;
    border: 1px solid #ccd0da;
}
QMenu::item:selected {
    background-color: #ccd0da;
}
QToolBar {
    background-color: #e6e9ef;
    border-bottom: 1px solid #ccd0da;
    spacing: 4px;
    padding: 2px;
}
QToolButton {
    background-color: #ccd0da;
    color: #4c4f69;
    border: 1px solid #bcc0cc;
    border-radius: 4px;
    padding: 4px 12px;
    margin: 2px;
}
QToolButton:hover {
    background-color: #bcc0cc;
}
QToolButton:pressed {
    background-color: #acb0be;
}
QToolButton:checked {
    background-color: #1e66f5;
    color: #eff1f5;
}
QStatusBar {
    background-color: #e6e9ef;
    color: #6c6f85;
    border-top: 1px solid #ccd0da;
}
QDockWidget { color: #4c4f69; }
QDockWidget::title {
    background-color: #e6e9ef;
    padding: 4px 8px;
    border-bottom: 1px solid #ccd0da;
}
QGroupBox {
    color: #4c4f69;
    border: 1px solid #ccd0da;
    border-radius: 6px;
    margin-top: 8px;
    padding-top: 16px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}
QTableView, QTreeView {
    background-color: #eff1f5;
    color: #4c4f69;
    gridline-color: #ccd0da;
    border: 1px solid #ccd0da;
    selection-background-color: #ccd0da;
    alternate-background-color: #e6e9ef;
}
QTableView::item, QTreeView::item { padding: 3px 6px; }
QHeaderView::section {
    background-color: #ccd0da;
    color: #4c4f69;
    padding: 4px 8px;
    border: 1px solid #bcc0cc;
    font-weight: bold;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #ffffff;
    color: #4c4f69;
    border: 1px solid #ccd0da;
    border-radius: 4px;
    padding: 4px 8px;
}
QLineEdit:focus, QSpinBox:focus { border-color: #1e66f5; }
QPushButton {
    background-color: #ccd0da;
    color: #4c4f69;
    border: 1px solid #bcc0cc;
    border-radius: 4px;
    padding: 6px 16px;
}
QPushButton:hover { background-color: #bcc0cc; }
QPushButton:pressed { background-color: #acb0be; }
QPushButton:disabled {
    background-color: #e6e9ef;
    color: #acb0be;
}
QPushButton#primaryBtn {
    background-color: #1e66f5;
    color: #eff1f5;
    border-color: #1e66f5;
    font-weight: bold;
}
QPushButton#primaryBtn:hover { background-color: #3d7cf7; }
QPushButton#dangerBtn {
    background-color: #d20f39;
    color: #eff1f5;
    border-color: #d20f39;
}
QCheckBox { color: #4c4f69; }
QLabel { color: #4c4f69; }
QProgressBar {
    background-color: #ccd0da;
    border: 1px solid #bcc0cc;
    border-radius: 4px;
    text-align: center;
    color: #4c4f69;
}
QProgressBar::chunk { background-color: #1e66f5; border-radius: 3px; }
QSplitter::handle { background-color: #ccd0da; margin: 1px; }
QScrollBar:vertical {
    background-color: #eff1f5;
    width: 10px;
    border: none;
}
QScrollBar::handle:vertical {
    background-color: #ccd0da;
    border-radius: 5px;
    min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
"""

# Color definitions for CAN table cells
CAN_COLORS = {
    "error_bg_dark": "#572630",
    "error_bg_light": "#f8d7da",
    "error_fg_dark": "#f38ba8",
    "error_fg_light": "#721c24",
    "extended_fg_dark": "#94e2d5",
    "extended_fg_light": "#179299",
    "rtr_fg_dark": "#f9e2af",
    "rtr_fg_light": "#df8e1d",
    "normal_fg_dark": "#cdd6f4",
    "normal_fg_light": "#4c4f69",
}


def get_theme_stylesheet(dark: bool = True) -> str:
    return DARK_THEME if dark else LIGHT_THEME
