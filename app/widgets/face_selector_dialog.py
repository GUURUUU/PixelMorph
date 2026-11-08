"""
Face selection dialog — shows all detected faces with red bounding boxes.
User clicks a face to select it as the source.
"""

from typing import List, Optional, Tuple

import cv2
import numpy as np
from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal
from PyQt6.QtGui import (QImage, QPixmap, QPainter, QPen, QColor,
                         QFont, QBrush, QMouseEvent, QPaintEvent)
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QWidget, QSizePolicy)
from app.logger import get_logger

log = get_logger(__name__)


class FaceThumbnail(QWidget):
    """Clickable face thumbnail with red box overlay."""

    clicked = pyqtSignal(int)

    def __init__(self, face_img: np.ndarray, index: int, score: float, parent=None):
        super().__init__(parent)
        self._index = index
        self._score = score
        self._face_img = face_img
        self._hovered = False
        self._selected = False

        self.setFixedSize(160, 160)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

    def set_selected(self, sel: bool):
        self._selected = sel
        self.update()

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Background
        bg_color = QColor(18, 24, 44) if not self._hovered else QColor(24, 32, 56)
        painter.fillRect(self.rect(), bg_color)

        # Face image
        if self._face_img is not None:
            h, w = self._face_img.shape[:2]
            scale = min(140 / w, 140 / h)
            new_w, new_h = int(w * scale), int(h * scale)
            rgb = cv2.cvtColor(self._face_img, cv2.COLOR_BGR2RGB)
            qimg = QImage(rgb.data, w, h, rgb.strides[0],
                          QImage.Format.Format_RGB888)
            pix = QPixmap.fromImage(qimg).scaled(
                new_w, new_h, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            x_off = (160 - new_w) // 2
            y_off = (160 - new_h) // 2
            painter.drawPixmap(x_off, y_off, pix)

        # Border glow
        border_color = QColor(0, 220, 100, 200) if self._selected else \
                       QColor(200, 40, 40, 150) if self._hovered else \
                       QColor(0, 150, 180, 60)
        pen = QPen(border_color, 2 if not self._selected else 3)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -2, -2), 4, 4)

        # Label
        painter.setPen(QColor(0, 220, 100) if self._selected else QColor(200, 200, 200))
        font = QFont("Consolas", 10, QFont.Weight.Bold)
        painter.setFont(font)
        label = f"#{self._index} ({self._score:.2f})"
        painter.drawText(QRect(0, self.height() - 20, self.width(), 20),
                         Qt.AlignmentFlag.AlignCenter, label)

        painter.end()

    def mousePressEvent(self, event: QMouseEvent):
        self._selected = True
        self.clicked.emit(self._index)
        self.update()

    def enterEvent(self, event):
        self._hovered = True
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        self.update()


class FaceSelectorDialog(QDialog):
    """
    Dialog showing all detected faces in the source image.
    User clicks one to select it.
    """

    face_selected = pyqtSignal(int, dict)  # index, face dict

    def __init__(self, source_image: np.ndarray, faces: List[dict],
                 parent=None):
        super().__init__(parent)
        log.info("FaceSelectorDialog opened with %d faces", len(faces))
        self._source_image = source_image
        self._faces = faces
        self._thumbnails: List[FaceThumbnail] = []

        self.setWindowTitle("Select Source Face")
        self.setMinimumSize(700, 400)
        self.setModal(True)

        self.setStyleSheet("""
            QDialog {
                background: rgba(8, 10, 22, 240);
                border: 2px solid rgba(0, 180, 200, 100);
                border-radius: 8px;
            }
        """)

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Title
        title = QLabel("Select a face to use as source")
        title.setStyleSheet("color: #00ccdd; font-size: 16px; font-weight: bold; padding: 8px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel(
            f"Detected {len(self._faces)} face(s) — click one to select")
        subtitle.setStyleSheet("color: #8098b0; font-size: 11px;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        # Thumbnail grid
        thumb_layout = QHBoxLayout()
        thumb_layout.setSpacing(12)
        thumb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        for i, face in enumerate(self._faces):
            bbox = face["bbox"]
            x1, y1, x2, y2 = [int(v) for v in bbox]
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(self._source_image.shape[1], x2)
            y2 = min(self._source_image.shape[0], y2)

            face_crop = self._source_image[y1:y2, x1:x2].copy()
            if face_crop.size == 0:
                # Fallback: use landmarks to crop
                lm = face["landmark_5"]
                cx = int(np.mean(lm[:, 0]))
                cy = int(np.mean(lm[:, 1]))
                size = 80
                x1 = max(0, cx - size)
                y1 = max(0, cy - size)
                x2 = min(self._source_image.shape[1], cx + size)
                y2 = min(self._source_image.shape[0], cy + size)
                face_crop = self._source_image[y1:y2, x1:x2].copy()

            if face_crop.size == 0:
                face_crop = np.zeros((128, 128, 3), dtype=np.uint8)

            thumb = FaceThumbnail(face_crop, i, face.get("score", 0.5))
            thumb.clicked.connect(self._on_face_clicked)
            self._thumbnails.append(thumb)
            thumb_layout.addWidget(thumb)

        layout.addLayout(thumb_layout)

        # Cancel button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("  Cancel  ")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: rgba(100, 100, 120, 40);
                color: #8098b0;
                border: 1px solid rgba(100, 100, 120, 60);
                border-radius: 4px;
                padding: 8px 24px;
            }
            QPushButton:hover {
                background: rgba(120, 120, 140, 60);
                color: #c8dcf0;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _on_face_clicked(self, index: int):
        """Handle face thumbnail click."""
        log.info("Face #%d selected in dialog (score=%.3f)", index,
                 self._faces[index].get("score", 0))
        # Deselect all others
        for i, thumb in enumerate(self._thumbnails):
            thumb.set_selected(i == index)

        self.face_selected.emit(index, self._faces[index])
        self.accept()
        log.debug("Face selector dialog closed with selection #%d", index)
