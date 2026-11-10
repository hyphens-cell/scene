from pathlib import Path

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    for role, color in (
        (QPalette.ColorRole.Window, "#0D111B"),
        (QPalette.ColorRole.WindowText, "#F1F5F9"),
        (QPalette.ColorRole.Base, "#101623"),
        (QPalette.ColorRole.AlternateBase, "#1B2335"),
        (QPalette.ColorRole.Text, "#F1F5F9"),
        (QPalette.ColorRole.Button, "#202A3D"),
        (QPalette.ColorRole.ButtonText, "#F1F5F9"),
        (QPalette.ColorRole.Highlight, "#8065ED"),
        (QPalette.ColorRole.HighlightedText, "#FFFFFF"),
        (QPalette.ColorRole.ToolTipBase, "#202632"),
        (QPalette.ColorRole.ToolTipText, "#F1F5F9"),
    ):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setFont(QFont("Segoe UI", 10))
    icon_root = (Path(__file__).parents[1] / "resources" / "icons").as_posix()
    app.setStyleSheet(STYLESHEET.replace("$ICON_ROOT", icon_root))


STYLESHEET = """
QWidget { color: #EDF1FA; font-family: 'Segoe UI'; font-size: 13px; }
QMainWindow, QDialog, QWidget#workspace { background: #0D111B; }
QWidget#panel, QFrame#panel { background: #171E2D; border: 1px solid #283247; border-radius: 12px; }
QWidget#toolbar { background: #171E2D; border: 1px solid #283247; border-radius: 10px; }
QWidget#navigation { background: #171E2D; border: 0; }
QWidget#mediaControls { background: #101725; border: 1px solid #303A52; border-radius: 10px; }
QLabel { border: 0; background: transparent; }
QLabel#muted { color: #9AA8BF; }
QLabel#eyebrow { color: #9EACC4; font-size: 11px; font-weight: 600; letter-spacing: 1px; }
QLabel#heading { font-size: 25px; font-weight: 700; color: #FFFFFF; }
QLabel#documentTitle { font-size: 14px; color: #DAE2F2; }
QLabel#timer { font-family: 'Consolas'; font-size: 25px; color: #E3E9F7; }
QLabel#counter { color: #C9D4EA; font-family: 'Consolas'; font-size: 15px; }
QLabel#live { color: #AAB8D0; background: #202A3D; padding: 6px 10px; border-radius: 6px; font-size: 11px; font-weight: 600; }
QLabel#live[state="live"] { color: #74E7C9; background: #17362F; }
QLabel#live[state="covered"] { color: #EBC68C; background: #382E21; }
QLabel#compatibilityWarning { color: #FCD58A; background: #30291E; padding: 8px; border-radius: 6px; }
QPushButton { background: #202A3D; border: 1px solid #344059; border-radius: 7px; padding: 7px 11px; min-height: 18px; }
QPushButton:hover { background: #2B3750; border-color: #7181A6; }
QPushButton:pressed { background: #35325E; }
QPushButton:checked { background: #58428F; border-color: #B59BFF; color: #FFFFFF; }
QPushButton:focus { border-color: #B9A8FF; }
QPushButton:disabled { color: #63718A; background: #171E2D; border-color: #283247; }
QPushButton#primary { background: #8065ED; border-color: #9880FF; color: #FFFFFF; font-weight: 600; }
QPushButton#primary:hover { background: #9278FB; }
QPushButton#primary:pressed { background: #6B50D6; }
QPushButton#primary:disabled { background: #292443; border-color: #393252; color: #807695; }
QPushButton#quiet { background: transparent; border-color: #303B51; }
QPushButton#quiet:hover { background: #263149; border-color: #7181A6; }
QPushButton#danger:hover { color: #FFBAC5; border-color: #AD6475; background: #3A2534; }
QPushButton#iconButton { padding: 7px; min-width: 18px; }
QPlainTextEdit, QLineEdit, QSpinBox, QComboBox { background: #101623; border: 1px solid #344059; border-radius: 6px; padding: 6px; selection-background-color: #8065ED; }
QPlainTextEdit { padding: 12px; }
QPlainTextEdit:focus, QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: #A28AF8; }
QSpinBox:disabled, QComboBox:disabled { color: #748099; border-color: #283247; }
QComboBox { padding-right: 20px; }
QComboBox::drop-down { width: 20px; border: 0; }
QComboBox::down-arrow { image: url("$ICON_ROOT/chevron-down.svg"); width: 12px; height: 12px; }
QSpinBox { padding-right: 20px; }
QSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 18px; background: #1B2538; border: 0; border-top-right-radius: 6px; }
QSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 18px; background: #1B2538; border: 0; border-bottom-right-radius: 6px; }
QSpinBox::up-arrow { image: url("$ICON_ROOT/chevron-up.svg"); width: 10px; height: 10px; }
QSpinBox::down-arrow { image: url("$ICON_ROOT/chevron-down.svg"); width: 10px; height: 10px; }
QComboBox QAbstractItemView { background: #202A3D; selection-background-color: #574783; padding: 4px; }
QListWidget { background: #101623; border: 0; outline: none; border-radius: 8px; }
QListWidget::item { border: 1px solid transparent; border-radius: 7px; padding: 7px; }
QListWidget::item:selected { background: #292741; border-color: #9B81F5; }
QListWidget::item:hover { background: #222D43; }
QListWidget#materialList::item { padding: 11px 9px; }
QSplitter::handle { background: #0D111B; }
QSplitter::handle:hover { background: #8065ED; }
QScrollArea { border: 0; background: transparent; }
QScrollBar:vertical { background: #101623; width: 8px; }
QScrollBar::handle:vertical { background: #3C4963; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: #101623; height: 8px; }
QScrollBar::handle:horizontal { background: #3C4963; border-radius: 4px; min-width: 24px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QMenuBar, QMenu { background: #111725; border: 0; }
QMenuBar::item { padding: 5px 10px; color: #A6B3CA; }
QMenuBar::item:selected, QMenu::item:selected { background: #393158; color: #FFFFFF; }
QMenu::item { padding: 7px 24px; }
QStatusBar { color: #9AA8BF; background: #111725; }
QStatusBar::item { border: 0; }
QTabWidget::pane { border: 1px solid #283247; border-radius: 10px; background: #171E2D; }
QTabBar::tab { background: transparent; color: #9AA8BF; padding: 10px 14px; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #D4C7FF; border-bottom-color: #9B81F5; }
QTableWidget { background: #101623; gridline-color: #283247; border: 0; }
QHeaderView::section { background: #202A3D; color: #9AA8BF; padding: 8px; border: 0; }
QToolTip { background: #202A3D; color: #F1F5F9; border: 1px solid #566580; padding: 6px; }
QSlider::groove:horizontal { height: 5px; border-radius: 2px; background: #303B50; }
QSlider::sub-page:horizontal { background: #9B81F5; border-radius: 2px; }
QSlider::handle:horizontal { background: #E5DBFF; width: 12px; margin: -4px 0; border-radius: 6px; }
QSlider::handle:horizontal:hover { background: #FFFFFF; }
QSlider::handle:horizontal:focus { border: 2px solid #BBA5FF; }
QSlider::sub-page:horizontal:disabled { background: #344059; }
QSlider::handle:horizontal:disabled { background: #63718A; }
"""
