"""
Control panel — right-side settings for PixelMorph.

Top section shows the loaded source face thumbnail.
Below: swap params, camera, display toggles, status, and control buttons.
"""

import traceback
from typing import Any, Callable, Dict, List, Optional

import cv2
import numpy as np
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap, QImage
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QComboBox,
    QCheckBox, QPushButton, QGroupBox, QScrollArea, QSpinBox,
    QDoubleSpinBox, QFileDialog, QGridLayout, QFrame, QSizePolicy,
)

from app.logger import get_logger
from .holographic_widgets import (
    HolographicSlider, GlowButton, StatusLED, SectionHeader, HolographicLabel,
)
from app.camera_enum import enumerate_cameras, find_best_camera

log = get_logger(__name__)


class CollapsibleSection(QWidget):
    """A collapsible section with header."""

    def __init__(self, title: str, expanded: bool = True, parent=None):
        super().__init__(parent)
        self._expanded = expanded
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.header = QPushButton(f"  {title}")
        self.header.setObjectName("sectionHeader")
        self.header.setFlat(True)
        self.header.setCheckable(True)
        self.header.setChecked(expanded)
        self.header.setStyleSheet("""
            QPushButton {
                text-align: left; color: #00ccdd; font-size: 12px;
                font-weight: bold; background: rgba(0,150,180,30);
                border: none; border-left: 3px solid #00ccdd;
                padding: 8px 8px 8px 12px; border-radius: 0;
            }
            QPushButton:hover { background: rgba(0,180,200,60); }
            QPushButton:checked { border-left: 3px solid #00eeff; }
        """)
        self.header.clicked.connect(self._toggle)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(4, 4, 4, 4)
        self.content_layout.setSpacing(6)

        layout.addWidget(self.header)
        layout.addWidget(self.content)
        self.content.setVisible(expanded)

    def _toggle(self):
        self._expanded = not self._expanded
        self.content.setVisible(self._expanded)

    def add_widget(self, widget: QWidget):
        self.content_layout.addWidget(widget)

    def add_layout(self, layout):
        self.content_layout.addLayout(layout)

    def add_row(self, label: str, widget: QWidget):
        row = QHBoxLayout()
        row.setSpacing(8)
        lbl = QLabel(label)
        lbl.setStyleSheet("color: #8098b0; font-size: 11px; min-width: 80px;")
        row.addWidget(lbl)
        row.addWidget(widget, 1)
        self.content_layout.addLayout(row)


class ControlPanel(QWidget):
    """Right-side control panel."""

    source_requested = pyqtSignal()
    start_stop_requested = pyqtSignal()
    recording_toggled = pyqtSignal(bool)
    snapshot_requested = pyqtSignal()
    settings_changed = pyqtSignal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("controlPanel")
        self.setMinimumWidth(320)
        self.setMaximumWidth(420)

        self._is_running = False
        self._recording = False
        self._cam_devices = []
        self._sliders = {}  # key -> (slider, min_v, max_v)

        self._build_ui()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(8)

        # ── Title ────────────────────────────────────
        title_row = QHBoxLayout()
        title = QLabel("⏣  PIXELMORPH")
        title.setObjectName("titleLabel")
        title.setFont(QFont("Consolas", 14, QFont.Weight.Bold))
        self._status_led = StatusLED(12)
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(self._status_led)
        main_layout.addLayout(title_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: rgba(0,180,200,40);")
        main_layout.addWidget(sep)

        # ── Scroll area ──────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll.setWidget(scroll_widget)
        sl = QVBoxLayout(scroll_widget)
        sl.setContentsMargins(2, 2, 2, 2)
        sl.setSpacing(6)

        # ════════════════════════════════════════════
        # SOURCE FACE
        # ════════════════════════════════════════════
        src_section = CollapsibleSection("SOURCE FACE", expanded=True)

        # Source face thumbnail
        self._source_thumb_label = QLabel()
        self._source_thumb_label.setFixedSize(140, 140)
        self._source_thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._source_thumb_label.setStyleSheet(
            "background: rgba(0,0,0,80); border: 1px solid #00ccdd; border-radius: 6px;")
        self._source_thumb_label.setText("no face\nloaded")
        thumb_row = QHBoxLayout()
        thumb_row.addStretch()
        thumb_row.addWidget(self._source_thumb_label)
        thumb_row.addStretch()

        self._source_path_label = QLabel("No source loaded")
        self._source_path_label.setStyleSheet("color: #6080a0; font-size: 10px;")
        self._source_path_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._load_source_btn = GlowButton("  ⚡ Load Source Face")
        self._load_source_btn.clicked.connect(self.source_requested.emit)

        self._source_faces_label = QLabel("")
        self._source_faces_label.setStyleSheet("color: #6080a0; font-size: 10px;")
        self._source_faces_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        src_section.add_layout(thumb_row)
        src_section.add_widget(self._source_path_label)
        src_section.add_widget(self._load_source_btn)
        src_section.add_widget(self._source_faces_label)
        sl.addWidget(src_section)

        # ════════════════════════════════════════════
        # SWAP SETTINGS
        # ════════════════════════════════════════════
        swap_section = CollapsibleSection("SWAP", expanded=True)

        self._model_combo = QComboBox()
        self._model_combo.addItems(["inswapper_128", "hyperswap_1a_256"])
        self._model_combo.currentTextChanged.connect(
            lambda v: self.settings_changed.emit("model", v))
        swap_section.add_row("Model", self._model_combo)

        self._pb_combo = QComboBox()
        for val in [128, 256, 384, 512, 768, 1024]:
            self._pb_combo.addItem(str(val), val)
        self._pb_combo.setCurrentIndex(2)
        self._pb_combo.currentIndexChanged.connect(
            lambda: self.settings_changed.emit("pixel_boost",
                                                self._pb_combo.currentData()))
        swap_section.add_row("Pixel Boost", self._pb_combo)

        swap_section.add_row("Blend", self._make_slider(0.0, 1.0, 0.5, 0.01, "weight"))
        swap_section.add_row("Resize", self._make_slider(0.25, 1.0, 0.75, 0.01, "resize"))
        swap_section.add_row("Threshold", self._make_slider(0.1, 1.0, 0.35, 0.01, "threshold"))

        self._skip_spin = QSpinBox()
        self._skip_spin.setRange(0, 10)
        self._skip_spin.setValue(2)
        self._skip_spin.valueChanged.connect(
            lambda v: self.settings_changed.emit("frame_skip", v))
        swap_section.add_row("Frame Skip", self._skip_spin)

        sl.addWidget(swap_section)

        # ════════════════════════════════════════════
        # CAMERA
        # ════════════════════════════════════════════
        cam_section = CollapsibleSection("CAMERA", expanded=False)

        self._cam_combo = QComboBox()
        self._scan_cameras_into_combo()
        self._cam_combo.currentIndexChanged.connect(
            lambda: self.settings_changed.emit("camera_device",
                                                self._cam_combo.currentData()))
        cam_section.add_row("Device", self._cam_combo)

        self._cam_res_combo = QComboBox()
        for lbl, (w, h) in [("640×480", (640, 480)),
                             ("1280×720", (1280, 720)),
                             ("1920×1080", (1920, 1080))]:
            self._cam_res_combo.addItem(lbl, (w, h))
        self._cam_res_combo.setCurrentIndex(1)
        self._cam_res_combo.currentIndexChanged.connect(self._on_cam_res_change)
        cam_section.add_row("Resolution", self._cam_res_combo)

        refresh_btn = GlowButton("  ⟳ Scan")
        refresh_btn.clicked.connect(self._scan_cameras)
        cam_section.add_widget(refresh_btn)

        sl.addWidget(cam_section)

        # ════════════════════════════════════════════
        # RECORDING
        # ════════════════════════════════════════════
        rec_section = CollapsibleSection("RECORDING", expanded=False)

        self._rec_fmt_combo = QComboBox()
        self._rec_fmt_combo.addItems(["MP4", "AVI", "MKV"])
        rec_section.add_row("Format", self._rec_fmt_combo)

        sl.addWidget(rec_section)

        # ════════════════════════════════════════════
        # DISPLAY
        # ════════════════════════════════════════════
        disp_section = CollapsibleSection("DISPLAY", expanded=False)

        self._show_landmarks_cb = QCheckBox("Face Landmarks")
        self._show_landmarks_cb.toggled.connect(
            lambda v: self.settings_changed.emit("show_landmarks", v))
        disp_section.add_widget(self._show_landmarks_cb)

        self._show_fps_cb = QCheckBox("FPS / Stats Overlay")
        self._show_fps_cb.setChecked(True)
        self._show_fps_cb.toggled.connect(
            lambda v: self.settings_changed.emit("show_fps", v))
        disp_section.add_widget(self._show_fps_cb)

        sep_disp = QFrame()
        sep_disp.setFrameShape(QFrame.Shape.HLine)
        sep_disp.setStyleSheet("color: rgba(0,180,200,30);")
        disp_section.add_widget(sep_disp)

        filter_label = QLabel("  QUALITY FILTERS")
        filter_label.setStyleSheet(
            "color: #6080a0; font-size: 10px; padding: 4px 0 2px 8px;")
        disp_section.add_widget(filter_label)

        self._clahe_cb = QCheckBox("Auto Contrast (CLAHE)")
        self._clahe_cb.toggled.connect(
            lambda v: self.settings_changed.emit("clahe", v))
        disp_section.add_widget(self._clahe_cb)

        self._sharpen_cb = QCheckBox("Sharpening")
        self._sharpen_cb.toggled.connect(
            lambda v: self.settings_changed.emit("sharpen", v))
        disp_section.add_widget(self._sharpen_cb)

        self._wb_cb = QCheckBox("Auto White Balance")
        self._wb_cb.toggled.connect(
            lambda v: self.settings_changed.emit("white_balance", v))
        disp_section.add_widget(self._wb_cb)

        self._color_match_cb = QCheckBox("Color Matching")
        self._color_match_cb.toggled.connect(
            lambda v: self.settings_changed.emit("color_match", v))
        disp_section.add_widget(self._color_match_cb)

        sl.addWidget(disp_section)

        # ── STATUS ──────────────────────────────────
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color: rgba(0,180,200,40);")
        sl.addWidget(sep2)

        self._status_label = QLabel("Ready — load a source face")
        self._status_label.setStyleSheet("color: #8098b0; font-size: 10px; padding: 4px;")
        self._status_label.setWordWrap(True)
        sl.addWidget(self._status_label)

        sl.addStretch(1)
        main_layout.addWidget(scroll, 1)

        # ── Control buttons ─────────────────────────
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)

        self._start_btn = QPushButton("  ▶  START  ")
        self._start_btn.setObjectName("startBtn")
        self._start_btn.clicked.connect(self._on_start_stop)
        btn_layout.addWidget(self._start_btn, 1)

        self._rec_btn = QPushButton("  ⏺ REC  ")
        self._rec_btn.setStyleSheet("""
            QPushButton {
                background: rgba(180,40,40,50); color: #cc6666;
                border: 1px solid rgba(200,40,40,60); border-radius: 5px;
                padding: 10px 12px; font-size: 11px;
            }
            QPushButton:hover {
                background: rgba(220,40,40,80);
                border: 1px solid rgba(255,40,40,100); color: #ff8888;
            }
        """)
        self._rec_btn.clicked.connect(self._on_rec_toggle)
        btn_layout.addWidget(self._rec_btn)

        self._snapshot_btn = QPushButton("  📷 SS  ")
        self._snapshot_btn.setStyleSheet("""
            QPushButton {
                background: rgba(40,120,180,50); color: #66aacc;
                border: 1px solid rgba(40,120,180,60); border-radius: 5px;
                padding: 10px 12px; font-size: 11px;
            }
            QPushButton:hover {
                background: rgba(60,160,220,80);
                border: 1px solid rgba(60,180,240,100); color: #88ccee;
            }
        """)
        self._snapshot_btn.clicked.connect(self.snapshot_requested.emit)
        btn_layout.addWidget(self._snapshot_btn)

        main_layout.addLayout(btn_layout)

    # ── Helpers ─────────────────────────────────────

    def _make_slider(self, min_v: float, max_v: float, default: float,
                     step: float, key: str) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        slider = HolographicSlider("", 0, 1000,
                                   int((default - min_v) / (max_v - min_v) * 1000))
        val_label = QLabel(f"{default:.2f}")
        val_label.setStyleSheet(
            "color: #00ccdd; font-family: Consolas; font-size: 10px; min-width: 40px;")
        val_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._sliders[key] = (slider, min_v, max_v, val_label)

        def _on_change(val: int):
            real = min_v + (val / 1000.0) * (max_v - min_v)
            val_label.setText(f"{real:.2f}")
            self.settings_changed.emit(key, round(real, 3))

        slider.valueChanged.connect(_on_change)
        layout.addWidget(slider, 1)
        layout.addWidget(val_label)
        return container

    def get_camera_device_name(self) -> str:
        """Friendly name of the currently selected camera (for settings)."""
        data = self._cam_combo.currentData()
        for i, name, _virt in self._cam_devices:
            if i == data:
                return name
        return ""

    def set_slider(self, key: str, value: float):
        """Programmatically set a registered slider to `value`."""
        entry = self._sliders.get(key)
        if entry is None:
            return
        _, min_v, max_v, val_label = entry
        val = int((value - min_v) / (max_v - min_v) * 1000)
        val = max(0, min(1000, val))
        slider = entry[0]
        slider.blockSignals(True)
        slider.setValue(val)
        slider.blockSignals(False)
        val_label.setText(f"{value:.2f}")

    # ── Camera ──────────────────────────────────────

    def _scan_cameras_into_combo(self):
        self._cam_combo.blockSignals(True)
        self._cam_combo.clear()
        self._cam_devices = enumerate_cameras()
        for idx, name, is_virtual in self._cam_devices:
            label = f"⚠ {name}" if is_virtual else name
            self._cam_combo.addItem(label, idx)
        if not self._cam_devices:
            self._cam_combo.addItem("No cameras found", -1)
        self._cam_combo.blockSignals(False)

        best = find_best_camera(self._cam_devices)
        idx = self._cam_combo.findData(best)
        if idx >= 0:
            self._cam_combo.setCurrentIndex(idx)

    def _scan_cameras(self):
        current = self._cam_combo.currentData()
        self._scan_cameras_into_combo()
        idx = self._cam_combo.findData(current)
        if idx >= 0:
            self._cam_combo.setCurrentIndex(idx)
        else:
            best = find_best_camera(self._cam_devices)
            idx = self._cam_combo.findData(best)
            if idx >= 0:
                self._cam_combo.setCurrentIndex(idx)

    def _on_cam_res_change(self, idx: int):
        data = self._cam_res_combo.currentData()
        if data:
            self.settings_changed.emit("camera_width", data[0])
            self.settings_changed.emit("camera_height", data[1])

    # ── Button handlers ─────────────────────────────

    def _on_start_stop(self):
        self._is_running = not self._is_running
        if self._is_running:
            self._start_btn.setText("  ⏹ STOP  ")
            self._start_btn.setStyleSheet("""
                QPushButton#startBtn {
                    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                        stop:0 #cc4444, stop:1 #882244);
                    color: white; font-weight: bold; border: none;
                    border-radius: 6px; padding: 10px 30px; font-size: 14px;
                }
            """)
            self._status_led.set_state("active")
        else:
            self._start_btn.setText("  ▶  START  ")
            self._start_btn.setStyleSheet("""
                QPushButton#startBtn {
                    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                        stop:0 #00cc88, stop:1 #0088aa);
                    color: #000000; font-weight: bold; border: none;
                    border-radius: 6px; padding: 10px 30px; font-size: 14px;
                }
            """)
            self._status_led.set_state("off")
        self.start_stop_requested.emit()

    def _on_rec_toggle(self):
        self._recording = not self._recording
        if self._recording:
            self._rec_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255,40,40,100); color: #ff6666;
                    border: 1px solid #ff4444; border-radius: 5px;
                    padding: 10px 12px; font-size: 11px;
                }
            """)
        else:
            self._rec_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(180,40,40,50); color: #cc6666;
                    border: 1px solid rgba(200,40,40,60); border-radius: 5px;
                    padding: 10px 12px; font-size: 11px;
                }
            """)
        self.recording_toggled.emit(self._recording)

    # ── Public API ──────────────────────────────────

    def set_status(self, text: str):
        self._status_label.setText(text)

    def set_source_path(self, path: str):
        name = path.split("/")[-1].split("\\")[-1]
        self._source_path_label.setText(f"📷 {name}")
        self._source_path_label.setStyleSheet("color: #00ccdd; font-size: 10px;")

    def set_source_thumbnail(self, thumb: np.ndarray):
        """Display the source face thumbnail in the control panel."""
        if thumb is None or thumb.size == 0:
            return
        h, w = thumb.shape[:2]
        max_dim = 130
        scale = max_dim / max(h, w)
        nw, nh = int(w * scale), int(h * scale)
        resized = cv2.resize(thumb, (nw, nh))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb.data, nw, nh, rgb.strides[0], QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(qimg)
        self._source_thumb_label.setPixmap(pix)
        self._source_thumb_label.setText("")
        log.debug("Source thumbnail set (%dx%d)", nw, nh)

    def set_faces_count(self, count: int, selected: int = 0):
        if count > 0:
            self._source_faces_label.setText(f"{count} face(s) detected | using face #{selected}")
        else:
            self._source_faces_label.setText("")

    def set_models(self, models: list):
        """Restrict the model dropdown to models present on disk."""
        if not models:
            return
        current = self._model_combo.currentText()
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        self._model_combo.addItems(models)
        idx = self._model_combo.findText(current)
        if idx >= 0:
            self._model_combo.setCurrentIndex(idx)
        self._model_combo.blockSignals(False)

    def set_recording_state(self, recording: bool):
        """Force the REC button indicator without re-emitting the signal."""
        self._recording = recording
        style_active = """
            QPushButton {
                background: rgba(255,40,40,100); color: #ff6666;
                border: 1px solid #ff4444; border-radius: 5px;
                padding: 10px 12px; font-size: 11px;
            }
        """
        style_idle = """
            QPushButton {
                background: rgba(180,40,40,50); color: #cc6666;
                border: 1px solid rgba(200,40,40,60); border-radius: 5px;
                padding: 10px 12px; font-size: 11px;
            }
        """
        self._rec_btn.setStyleSheet(style_active if recording else style_idle)

    def set_running(self, running: bool):
        if running != self._is_running:
            self._on_start_stop()

    def get_setting(self, key: str):
        mapping = {
            "model": lambda: self._model_combo.currentText(),
            "pixel_boost": lambda: self._pb_combo.currentData(),
            "threshold": lambda: self._slider_value("threshold", 0.35),
            "weight": lambda: self._slider_value("weight", 0.5),
            "resize": lambda: self._slider_value("resize", 0.75),
            "frame_skip": lambda: self._skip_spin.value(),
            "camera_device": lambda: self._cam_combo.currentData(),
            "clahe": lambda: self._clahe_cb.isChecked(),
            "sharpen": lambda: self._sharpen_cb.isChecked(),
            "white_balance": lambda: self._wb_cb.isChecked(),
            "color_match": lambda: self._color_match_cb.isChecked(),
            "show_landmarks": lambda: self._show_landmarks_cb.isChecked(),
            "show_fps": lambda: self._show_fps_cb.isChecked(),
            "show_stats": lambda: self._show_fps_cb.isChecked(),
            "recording_format": lambda: self._rec_fmt_combo.currentText().lower(),
        }
        fn = mapping.get(key)
        return fn() if fn else None

    def _slider_value(self, key: str, default: float):
        entry = self._sliders.get(key)
        if entry is None:
            return None
        slider, min_v, max_v = entry[0], entry[1], entry[2]
        return round(min_v + slider.value() / 1000.0 * (max_v - min_v), 3)

    def load_settings(self, settings: Dict[str, Any]):
        log.debug("Loading %d settings into UI", len(settings))
        if "model" in settings:
            idx = self._model_combo.findText(settings["model"])
            if idx >= 0:
                self._model_combo.setCurrentIndex(idx)
        if "pixel_boost" in settings:
            idx = self._pb_combo.findData(settings["pixel_boost"])
            if idx >= 0:
                self._pb_combo.setCurrentIndex(idx)
        # Camera: restore by device NAME, but only for real (non-virtual)
        # cams — never resurrect a stale selection pointing at a virtual cam.
        cam_restore_idx = None
        if "camera_device_name" in settings:
            saved = settings["camera_device_name"]
            match = next(
                ((i, n, v) for (i, n, v) in self._cam_devices
                 if n == saved and not v), None)
            if match:
                found = self._cam_combo.findData(match[0])
                cam_restore_idx = found if found >= 0 else None
            else:
                log.info("Saved camera '%s' not found or virtual — auto-selecting best real camera", saved)
        elif "camera_device" in settings:
            # Legacy index-based restore — only if it points at a real cam
            idx_data = next(
                ((i, n, v) for (i, n, v) in self._cam_devices
                 if i == settings["camera_device"] and not v), None)
            if idx_data:
                found = self._cam_combo.findData(idx_data[0])
                cam_restore_idx = found if found >= 0 else None
        if cam_restore_idx is not None:
            self._cam_combo.setCurrentIndex(cam_restore_idx)
        if "frame_skip" in settings:
            self._skip_spin.setValue(settings["frame_skip"])
        for key in ("threshold", "weight", "resize"):
            if key in settings:
                self.set_slider(key, float(settings[key]))
        if "clahe" in settings:
            self._clahe_cb.setChecked(settings["clahe"])
        if "sharpen" in settings:
            self._sharpen_cb.setChecked(settings["sharpen"])
        if "white_balance" in settings:
            self._wb_cb.setChecked(settings["white_balance"])
        if "color_match" in settings:
            self._color_match_cb.setChecked(settings["color_match"])
        if "show_landmarks" in settings:
            self._show_landmarks_cb.setChecked(settings["show_landmarks"])
        if "show_fps" in settings:
            self._show_fps_cb.setChecked(settings["show_fps"])
