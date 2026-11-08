"""
Preview panels — clean two-mode display.

INPUT  (left)  — camera feed + detection overlays (boxes, landmarks, FPS, stats)
OUTPUT (right) — clean swap result, nothing else.
"""

from typing import List, Optional, Tuple

import cv2
import numpy as np
from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal
from PyQt6.QtGui import (QImage, QPixmap, QPainter, QPen, QColor,
                         QFont, QBrush, QPaintEvent, QMouseEvent)
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
from app.logger import get_logger

log = get_logger(__name__)


class PreviewWidget(QWidget):
    """Single preview panel. Shows a frame with optional overlays."""

    face_clicked = pyqtSignal(int)  # index of face clicked

    def __init__(self, title: str = "", subtitle: str = "",
                 show_overlays: bool = True, parent=None):
        super().__init__(parent)
        self._title = title
        self._subtitle = subtitle
        self._show_overlays = show_overlays

        # Frame & detection data
        self._frame: Optional[np.ndarray] = None
        self._faces: List[dict] = []
        self._selected_face_idx: int = -1
        self._show_landmarks: bool = False
        self._show_fps: bool = True

        # Overlay text
        self._fps_text: str = ""
        self._stats_text: str = ""

        # Layout helpers
        self._scale: float = 1.0
        self._offset: Tuple[int, int] = (0, 0)

        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)

        if show_overlays:
            self.setMouseTracking(True)
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setMouseTracking(False)
            self.setCursor(Qt.CursorShape.ArrowCursor)

    # ── Public API ──────────────────────────────────

    def set_frame(self, frame: Optional[np.ndarray]):
        self._frame = frame
        self.update()

    def set_faces(self, faces: List[dict]):
        self._faces = faces
        self.update()

    def set_selected_face(self, idx: int):
        self._selected_face_idx = idx
        self.update()

    def set_show_landmarks(self, show: bool):
        self._show_landmarks = show
        self.update()

    def set_show_fps(self, show: bool):
        self._show_fps = show
        self.update()

    def set_fps_text(self, text: str):
        self._fps_text = text

    def set_stats_text(self, text: str):
        self._stats_text = text

    # ── Coordinate mapping ───────────────────────────

    def _frame_to_widget(self, fx: float, fy: float) -> QPoint:
        return QPoint(int(fx * self._scale + self._offset[0]),
                      int(fy * self._scale + self._offset[1]))

    def _widget_to_frame(self, wx: int, wy: int) -> Tuple[float, float]:
        fx = (wx - self._offset[0]) / self._scale
        fy = (wy - self._offset[1]) / self._scale
        return fx, fy

    # ── Events ───────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        if not self._show_overlays or self._frame is None:
            return
        fx, fy = self._widget_to_frame(event.position().x(), event.position().y())
        for i, face in enumerate(self._faces):
            x1, y1, x2, y2 = face["bbox"]
            if x1 <= fx <= x2 and y1 <= fy <= y2:
                log.info("Face #%d clicked (score=%.3f)", i, face.get("score", 0))
                self._selected_face_idx = i
                self.face_clicked.emit(i)
                self.update()
                return

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w_w, w_h = self.width(), self.height()

        # ── Background ──────────────────────────────
        painter.fillRect(self.rect(), QColor(8, 10, 22))

        if self._frame is None:
            # Placeholder
            painter.setPen(QColor(60, 80, 100))
            font = QFont("Segoe UI", 13)
            painter.setFont(font)
            lines = self._title
            if self._subtitle:
                lines += f"\n{self._subtitle}"
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, lines)
            painter.end()
            return

        # ── Scale frame ─────────────────────────────
        h, w = self._frame.shape[:2]
        scale = min(w_w / w, w_h / h) * 0.95
        self._scale = scale
        new_w = int(w * scale)
        new_h = int(h * scale)
        self._offset = ((w_w - new_w) // 2, (w_h - new_h) // 2)

        rgb = cv2.cvtColor(self._frame, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb.data, w, h, rgb.strides[0], QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(qimg).scaled(
            new_w, new_h, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        painter.drawPixmap(self._offset[0], self._offset[1], pix)

        # ── Overlays (only when enabled) ────────────
        if self._show_overlays:
            self._draw_overlays(painter, new_w, new_h)

        # Subtle border
        pen = QPen(QColor(0, 180, 200, 60), 1)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(
            self._offset[0] - 1, self._offset[1] - 1,
            new_w + 2, new_h + 2, 2, 2)
        painter.end()

    def _draw_overlays(self, painter: QPainter, new_w: int, new_h: int):
        """Draw face boxes, landmarks, labels, and FPS/stats text."""
        for i, face in enumerate(self._faces):
            bbox = face["bbox"]
            p1 = self._frame_to_widget(bbox[0], bbox[1])
            p2 = self._frame_to_widget(bbox[2], bbox[3])

            is_sel = (i == self._selected_face_idx)
            color = QColor(0, 220, 100) if is_sel else QColor(200, 40, 40)
            painter.setPen(QPen(color, 3 if is_sel else 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRect(p1, p2))

            # Landmarks
            if self._show_landmarks and "landmark_5" in face:
                for pt in face["landmark_5"]:
                    lp = self._frame_to_widget(pt[0], pt[1])
                    painter.setBrush(QBrush(QColor(0, 220, 255, 180)))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawEllipse(lp, 3, 3)

            # Label
            label = f"#{i} ({face['score']:.2f})"
            painter.setPen(QPen(QColor(0, 220, 100) if is_sel else QColor(255, 80, 80)))
            font = QFont("Consolas", 9, QFont.Weight.Bold)
            painter.setFont(font)
            painter.drawText(QPoint(p1.x() + 4, p1.y() - 6), label)

        # FPS / Stats
        if self._show_fps and (self._fps_text or self._stats_text):
            painter.setPen(QColor(0, 220, 100))
            font = QFont("Consolas", 10)
            painter.setFont(font)
            y_base = self._offset[1] + new_h - 10
            if self._fps_text:
                painter.drawText(self._offset[0] + 8, y_base, self._fps_text)
                y_base -= 18
            if self._stats_text:
                painter.drawText(self._offset[0] + 8, y_base, self._stats_text)


class SideBySidePanel(QWidget):
    """Two previews side by side: INPUT (left, overlays) and OUTPUT (right, clean)."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.input_preview = PreviewWidget(
            title="[ INPUT ]",
            subtitle="camera feed + detection",
            show_overlays=True,
        )
        self.output_preview = PreviewWidget(
            title="[ OUTPUT ]",
            subtitle="swap result",
            show_overlays=False,
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Input wrapper
        in_w = QVBoxLayout()
        in_w.setContentsMargins(0, 0, 0, 0)
        in_w.setSpacing(0)
        lbl_in = QLabel("◉  INPUT")
        lbl_in.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_in.setStyleSheet("font-size: 12px; color: #00ccdd; padding: 2px;")
        sub_in = QLabel("camera + detection overlays")
        sub_in.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_in.setStyleSheet("font-size: 9px; color: #406080; padding: 0px 0px 4px 0px;")
        in_w.addWidget(lbl_in)
        in_w.addWidget(sub_in)
        in_w.addWidget(self.input_preview, 1)
        in_frame = QWidget()
        in_frame.setLayout(in_w)
        in_frame.setObjectName("panel")
        in_frame.setStyleSheet(
            "QWidget#panel { background: rgba(12,18,38,180); border: 1px solid rgba(0,150,180,70); border-radius: 6px; }")
        layout.addWidget(in_frame, 1)

        # Output wrapper
        out_w = QVBoxLayout()
        out_w.setContentsMargins(0, 0, 0, 0)
        out_w.setSpacing(0)
        lbl_out = QLabel("◉  OUTPUT")
        lbl_out.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_out.setStyleSheet("font-size: 12px; color: #00cc88; padding: 2px;")
        sub_out = QLabel("clean swap result")
        sub_out.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_out.setStyleSheet("font-size: 9px; color: #406080; padding: 0px 0px 4px 0px;")
        out_w.addWidget(lbl_out)
        out_w.addWidget(sub_out)
        out_w.addWidget(self.output_preview, 1)
        out_frame = QWidget()
        out_frame.setLayout(out_w)
        out_frame.setObjectName("panel")
        out_frame.setStyleSheet(
            "QWidget#panel { background: rgba(12,18,38,180); border: 1px solid rgba(0,150,180,70); border-radius: 6px; }")
        layout.addWidget(out_frame, 1)
