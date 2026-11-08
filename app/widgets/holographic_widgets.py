"""
Custom holographic-themed widgets for PixelMorph.
"""

from PyQt6.QtCore import Qt, QTimer, QRect, QSize
from PyQt6.QtGui import QPainter, QColor, QLinearGradient, QFont, QBrush, QPen, QPaintEvent
from PyQt6.QtWidgets import (QSlider, QWidget, QHBoxLayout, QVBoxLayout,
                             QLabel, QPushButton)
from app.logger import get_logger

log = get_logger(__name__)


class HolographicSlider(QSlider):
    """Slider with glowing cyan track and value display."""

    def __init__(self, label: str = "", min_val: int = 0, max_val: int = 100,
                 default: int = 50, orientation: Qt.Orientation = Qt.Orientation.Horizontal,
                 parent=None):
        super().__init__(orientation, parent)

        self._label_text = label
        self._glow = 0

        self.setMinimum(min_val)
        self.setMaximum(max_val)
        self.setValue(default)
        self.setTickPosition(QSlider.TickPosition.NoTicks)
        self.setFixedHeight(30 if orientation == Qt.Orientation.Horizontal else 200)

        # Glow animation timer
        self._glow_timer = QTimer(self)
        self._glow_timer.timeout.connect(self._animate_glow)
        self._glow_timer.start(50)

    def _animate_glow(self):
        self._glow = (self._glow + 1) % 100
        if self.isSliderDown():
            self.update()

    def paintEvent(self, event: QPaintEvent):
        super().paintEvent(event)
        if not self.isSliderDown():
            return

        # Draw glow ring around handle when dragging
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        groove_rect = self.rect().adjusted(8, 10, -8, -10)
        val_range = self.maximum() - self.minimum()
        ratio = (self.value() - self.minimum()) / max(val_range, 1)
        handle_x = int(groove_rect.left() + ratio * groove_rect.width())

        glow_size = 28 + int(8 * abs(self._glow / 50.0 - 1))
        glow_color = QColor(0, 200, 230, 60 + int(30 * abs(self._glow / 50.0 - 1)))
        painter.setBrush(QBrush(glow_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRect(handle_x - glow_size//2, self.height()//2 - glow_size//2,
                                  glow_size, glow_size))
        painter.end()


class GlowButton(QPushButton):
    """Button with hover glow effect and cyan border."""

    def __init__(self, text: str = "", parent=None, primary: bool = False):
        super().__init__(text, parent)
        self._primary = primary
        self._hover = False
        self._glow = 0

        self.setMouseTracking(True)
        self.setMinimumHeight(32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Glow animation
        self._glow_timer = QTimer(self)
        self._glow_timer.timeout.connect(self._animate)
        self._glow_timer.start(40)

    def _animate(self):
        if self._hover or self.isDown():
            self._glow = (self._glow + 1) % 100
            self.update()

    def enterEvent(self, event):
        self._hover = True
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self._glow = 0
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._hover and not self.isDown():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Outer glow
        glow_intensity = int(40 * (1 - abs(self._glow / 50.0 - 1)))
        if self._primary:
            glow_color = QColor(0, 220, 120, glow_intensity)
        else:
            glow_color = QColor(0, 220, 255, glow_intensity)

        pen = QPen(glow_color, 2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -2, -2), 6, 6)

        painter.end()


class StatusLED(QWidget):
    """Small LED indicator (green = active, red = error, off = gray)."""

    def __init__(self, size: int = 10, parent=None):
        super().__init__(parent)
        self._state = "off"  # off | active | error
        self.setFixedSize(size, size)

    def set_state(self, state: str):
        self._state = state
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        colors = {
            "off": QColor(40, 50, 60),
            "active": QColor(0, 220, 100),
            "error": QColor(220, 40, 40),
            "warning": QColor(255, 160, 20),
        }
        color = colors.get(self._state, colors["off"])

        # Outer glow
        glow = QColor(color.red(), color.green(), color.blue(), 60)
        painter.setBrush(QBrush(glow))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(self.rect().adjusted(-2, -2, 2, 2))

        # Inner dot
        painter.setBrush(QBrush(color))
        painter.drawEllipse(self.rect().adjusted(2, 2, -2, -2))
        painter.end()


class SectionHeader(QLabel):
    """Section header with left cyan accent bar."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName("sectionHeader")
        self.setContentsMargins(12, 4, 4, 2)


class HolographicLabel(QLabel):
    """Label with monospace cyan-tinted text."""

    def __init__(self, text: str = "", mono: bool = True, parent=None):
        super().__init__(text, parent)
        font = QFont("Consolas" if mono else "Segoe UI", 11)
        font.setBold(True)
        self.setFont(font)
        self.setStyleSheet("color: #00ccdd; background: transparent;")
