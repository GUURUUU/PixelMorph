"""
Holographic neon theme for PixelMorph.
Dark glassmorphism with cyan/teal accents, glowing borders, sci-fi HUD aesthetic.
"""

from PyQt6.QtGui import QColor, QPalette, QFont
from app.logger import get_logger

log = get_logger(__name__)

# ── Color palette ──────────────────────────────────────────────────────────
DARK_BG       = QColor(8, 10, 22)         # Near-black with blue tint
PANEL_BG      = QColor(12, 18, 38, 210)   # Semi-transparent dark blue
PANEL_BORDER  = QColor(0, 180, 200, 120)  # Glowing cyan border
ACCENT        = QColor(0, 200, 220)        # Primary cyan
ACCENT_GLOW   = QColor(0, 220, 255, 80)   # Glow
ACCENT_DIM    = QColor(0, 150, 180)        # Dimmer cyan
GREEN         = QColor(0, 220, 100)        # Success / active
RED           = QColor(220, 40, 40)        # Danger / recording
ORANGE        = QColor(255, 160, 20)       # Warning
TEXT_PRIMARY  = QColor(200, 220, 240)      # Light blue-white
TEXT_SECONDARY= QColor(120, 150, 180)      # Muted
TEXT_DIM      = QColor(60, 80, 100)        # Very muted
SCANLINE      = QColor(0, 180, 200, 12)    # Subtle scanline overlay


# ── Fonts ──────────────────────────────────────────────────────────────────
FONT_FAMILY      = "Segoe UI"
FONT_MONO        = "Cascadia Code, Consolas, Courier New"
FONT_SIZE_SMALL  = 10
FONT_SIZE_NORMAL = 12
FONT_SIZE_LARGE  = 16
FONT_SIZE_HUGE   = 22


def get_font(size: int = FONT_SIZE_NORMAL, bold: bool = False,
             mono: bool = False) -> QFont:
    f = QFont(FONT_MONO if mono else FONT_FAMILY, size)
    f.setBold(bold)
    return f


# ── Global QSS stylesheet ──────────────────────────────────────────────────
GLOBAL_QSS = """
/* ── Root ────────────────────────────────────────── */
QMainWindow, QDialog, QWidget#centralWidget {
    background-color: #080a16;
}

/* ── Panels (glassmorphism) ──────────────────────── */
QFrame#panel, QGroupBox, QWidget#controlPanel, QWidget#previewPanel {
    background: rgba(12, 18, 38, 200);
    border: 1px solid rgba(0, 180, 200, 80);
    border-radius: 8px;
    padding: 4px;
}

/* ── Labels ──────────────────────────────────────── */
QLabel {
    color: #c8dcf0;
    background: transparent;
    border: none;
    font-size: 12px;
}
QLabel#sectionHeader {
    color: #00ccdd;
    font-size: 13px;
    font-weight: bold;
    border: none;
    border-left: 3px solid #00ccdd;
    padding-left: 8px;
    margin-top: 6px;
    margin-bottom: 4px;
}
QLabel#statusValue {
    color: #00dc64;
    font-family: Consolas, "Courier New", monospace;
    font-size: 11px;
}
QLabel#titleLabel {
    color: #00e0f0;
    font-size: 18px;
    font-weight: bold;
    border: none;
}

/* ── Buttons ─────────────────────────────────────── */
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop: 0 rgba(0, 180, 220, 80),
        stop: 0.5 rgba(0, 140, 180, 60),
        stop: 1 rgba(0, 100, 140, 40));
    color: #c8dcf0;
    border: 1px solid rgba(0, 180, 200, 100);
    border-radius: 5px;
    padding: 6px 16px;
    font-size: 12px;
    min-height: 24px;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop: 0 rgba(0, 200, 240, 120),
        stop: 0.5 rgba(0, 160, 200, 100),
        stop: 1 rgba(0, 120, 160, 80));
    border: 1px solid rgba(0, 220, 255, 180);
}
QPushButton:pressed {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop: 0 rgba(0, 120, 180, 150),
        stop: 1 rgba(0, 80, 140, 120));
}
QPushButton#startBtn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop: 0 #00cc88,
        stop: 1 #0088aa);
    color: #000000;
    font-weight: bold;
    border: none;
    border-radius: 6px;
    padding: 10px 30px;
    font-size: 14px;
}
QPushButton#startBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop: 0 #00eeaa,
        stop: 1 #00aadd);
}
QPushButton#dangerBtn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop: 0 #cc2222,
        stop: 1 #991133);
    color: white;
    font-weight: bold;
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
}
QPushButton#dangerBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop: 0 #ee3333,
        stop: 1 #bb2244);
}

/* ── Combo / Dropdown ────────────────────────────── */
QComboBox {
    background: rgba(12, 18, 38, 220);
    color: #c8dcf0;
    border: 1px solid rgba(0, 180, 200, 80);
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 11px;
    min-height: 20px;
}
QComboBox:hover {
    border: 1px solid rgba(0, 200, 220, 150);
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #00ccdd;
    margin-right: 4px;
}
QComboBox QAbstractItemView {
    background: rgba(8, 12, 28, 240);
    color: #c8dcf0;
    border: 1px solid rgba(0, 180, 200, 100);
    selection-background-color: rgba(0, 180, 220, 120);
    outline: none;
}

/* ── Sliders ─────────────────────────────────────── */
QSlider::groove:horizontal {
    border: none;
    height: 4px;
    background: rgba(60, 80, 120, 100);
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.6,
        stop: 0 #00ddff,
        stop: 0.5 #00aacc,
        stop: 1 #008899);
    border: 1px solid #00eeff;
    width: 14px;
    height: 14px;
    margin: -6px 0;
    border-radius: 7px;
}
QSlider::handle:horizontal:hover {
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.6,
        stop: 0 #44eeff,
        stop: 1 #00ccdd);
    width: 16px;
    height: 16px;
    margin: -7px 0;
    border-radius: 8px;
}
QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop: 0 #00aacc,
        stop: 1 #00ddff);
    border-radius: 2px;
}

/* ── SpinBox ─────────────────────────────────────── */
QSpinBox, QDoubleSpinBox {
    background: rgba(12, 18, 38, 220);
    color: #c8dcf0;
    border: 1px solid rgba(0, 180, 200, 80);
    border-radius: 4px;
    padding: 2px 4px;
    font-size: 11px;
    min-height: 20px;
}
QSpinBox:hover, QDoubleSpinBox:hover {
    border: 1px solid rgba(0, 200, 220, 150);
}
QSpinBox::up-button, QDoubleSpinBox::up-button {
    border: none;
    background: transparent;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    border: none;
    background: transparent;
}

/* ── CheckBox ────────────────────────────────────── */
QCheckBox {
    color: #c8dcf0;
    font-size: 11px;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid rgba(0, 180, 200, 100);
    border-radius: 3px;
    background: rgba(12, 18, 38, 200);
}
QCheckBox::indicator:checked {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop: 0 #00aacc, stop: 1 #0088aa);
    border: 1px solid #00ddff;
}

/* ── GroupBox ────────────────────────────────────── */
QGroupBox {
    background: rgba(12, 18, 38, 160);
    border: 1px solid rgba(0, 150, 180, 70);
    border-radius: 6px;
    margin-top: 14px;
    padding-top: 16px;
    font-size: 11px;
    color: #00ccdd;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px 0 6px;
    color: #00ccdd;
}

/* ── ScrollArea ──────────────────────────────────── */
QScrollArea {
    border: none;
    background: transparent;
}
QScrollBar:vertical {
    background: rgba(12, 18, 38, 100);
    width: 8px;
    margin: 0;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: rgba(0, 180, 200, 80);
    min-height: 30px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: rgba(0, 200, 220, 130);
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}

/* ── Tab Widget ──────────────────────────────────── */
QTabWidget::pane {
    background: rgba(12, 18, 38, 180);
    border: 1px solid rgba(0, 150, 180, 70);
    border-radius: 6px;
    top: -1px;
}
QTabBar::tab {
    background: rgba(12, 18, 38, 120);
    color: #8090a0;
    border: 1px solid rgba(0, 150, 180, 40);
    border-bottom: none;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
    padding: 6px 14px;
    font-size: 11px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background: rgba(12, 18, 38, 200);
    color: #00ddff;
    border: 1px solid rgba(0, 180, 200, 100);
    border-bottom: 1px solid rgba(12, 18, 38, 200);
}
QTabBar::tab:hover:!selected {
    color: #a0c0d0;
}

/* ── ProgressBar ─────────────────────────────────── */
QProgressBar {
    background: rgba(12, 18, 38, 180);
    border: 1px solid rgba(0, 150, 180, 60);
    border-radius: 3px;
    text-align: center;
    color: transparent;
    font-size: 10px;
    height: 6px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop: 0 #00aacc, stop: 1 #00eeff);
    border-radius: 2px;
}

/* ── LineEdit ────────────────────────────────────── */
QLineEdit {
    background: rgba(12, 18, 38, 220);
    color: #c8dcf0;
    border: 1px solid rgba(0, 180, 200, 80);
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 11px;
}
QLineEdit:focus {
    border: 1px solid #00ccdd;
}

/* ── Tooltips ────────────────────────────────────── */
QToolTip {
    background: rgba(8, 10, 30, 240);
    color: #c8dcf0;
    border: 1px solid rgba(0, 180, 200, 120);
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 11px;
}
"""


def apply_theme(app) -> None:
    """Apply the holographic neon theme to the QApplication."""
    log.debug("Applying holographic neon theme...")
    app.setStyle("Fusion")
    app.setStyleSheet(GLOBAL_QSS)
    log.debug("Theme applied (QSS: %d chars)", len(GLOBAL_QSS))

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, DARK_BG)
    palette.setColor(QPalette.ColorRole.WindowText, TEXT_PRIMARY)
    palette.setColor(QPalette.ColorRole.Base, PANEL_BG)
    palette.setColor(QPalette.ColorRole.Text, TEXT_PRIMARY)
    palette.setColor(QPalette.ColorRole.Button, PANEL_BG)
    palette.setColor(QPalette.ColorRole.ButtonText, TEXT_PRIMARY)
    palette.setColor(QPalette.ColorRole.Highlight, ACCENT)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(8, 10, 30))
    palette.setColor(QPalette.ColorRole.ToolTipText, TEXT_PRIMARY)
    app.setPalette(palette)
