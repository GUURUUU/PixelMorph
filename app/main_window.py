"""
Main window — PixelMorph face swap application.

Clear separation:
  LEFT  = INPUT  → camera feed + detection overlays (when running)
  RIGHT = OUTPUT → clean swap result (when running)
  Source face shown as thumbnail in the control panel only.
"""

import os
import sys
import time
import threading
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QAction, QCloseEvent, QFont, QPixmap, QImage
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QFileDialog, QMessageBox, QApplication, QSplitter,
)

from app.logger import get_logger
from .widgets.preview_widget import SideBySidePanel
from .widgets.control_panel import ControlPanel
from .widgets.face_selector_dialog import FaceSelectorDialog
from .settings_manager import SettingsManager
from .face_engine import FaceEngine
from .filters import (
    apply_clahe, apply_sharpen, apply_white_balance, apply_color_match,
)
from .virtual_cam import VirtualCameraOutput
from .bestcam_bridge import BestCamBridge
from .recorder import Recorder
from .styles import apply_theme

log = get_logger(__name__)


class ProcessingThread(QObject):
    """Runs the face swap loop in a background thread."""

    frame_ready = pyqtSignal(np.ndarray, np.ndarray)  # input_frame, output_frame
    faces_detected = pyqtSignal(list, int)  # faces list, selected_idx
    status_update = pyqtSignal(str)
    stats_update = pyqtSignal(str, str)  # fps_text, stats_text
    error_occurred = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Shared state (set from main thread before start / during run)
        self.source_embedding: Optional[np.ndarray] = None
        self.camera_device: int = 0
        self.cam_width: int = 1280
        self.cam_height: int = 720
        self.model: str = "hyperswap_1a_256"
        self.pixel_boost: int = 512
        self.weight: float = 0.5
        self.resize: float = 0.75
        self.frame_skip: int = 2
        self.threshold: float = 0.35
        self.output_mode: str = "window"

        # Post-processing filter flags
        self.clahe: bool = False
        self.sharpen: bool = False
        self.white_balance: bool = False
        self.color_match: bool = False

        self.engine: Optional[FaceEngine] = None
        self.vcam: Optional[VirtualCameraOutput] = None
        self.bestcam: Optional[BestCamBridge] = None
        self.recorder: Optional[Recorder] = None

        # Internal
        self._target_faces: List[dict] = []
        self._selected_face_idx: int = 0
        self._lock = threading.Lock()
        self._current_frame: Optional[np.ndarray] = None

        log.debug("ProcessingThread created")

    @property
    def running(self) -> bool:
        return self._running

    def start(self, engine: FaceEngine, vcam: Optional[VirtualCameraOutput] = None,
              bestcam: Optional[BestCamBridge] = None,
              recorder: Optional[Recorder] = None):
        if self._running:
            return
        self.engine = engine
        self.vcam = vcam
        self.bestcam = bestcam
        self.recorder = recorder
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="processing-thread")
        self._thread.start()
        log.info("Processing started (cam=%d model=%s pb=%d resize=%.2f skip=%d)",
                 self.camera_device, self.model, self.pixel_boost,
                 self.resize, self.frame_skip)

    def stop(self):
        log.info("Stopping processing thread...")
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
            if self._thread.is_alive():
                log.warning("Processing thread did not stop within 3s")
            self._thread = None
        log.info("Processing thread stopped")

    def set_source_embedding(self, emb: np.ndarray):
        with self._lock:
            self.source_embedding = emb.copy()

    def get_current_frame(self) -> Optional[np.ndarray]:
        with self._lock:
            return self._current_frame

    def _apply_post_filters(self, frame: np.ndarray,
                            original: np.ndarray) -> np.ndarray:
        """Apply post-processing filters to *frame* before display/record."""
        out = frame.copy()

        if self.white_balance:
            out = apply_white_balance(out)
        if self.clahe:
            out = apply_clahe(out)
        if self.color_match and original is not None and original.size > 0:
            out = apply_color_match(out, original)
        if self.sharpen:
            out = apply_sharpen(out)

        return out

    def _run(self):
        """Main processing loop — reads camera, detects faces, swaps, emits."""
        cap = None
        try:
            cap = cv2.VideoCapture(self.camera_device, cv2.CAP_DSHOW)
            if not cap.isOpened():
                self.error_occurred.emit(f"Cannot open camera {self.camera_device}")
                self._running = False
                return
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.cam_width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cam_height)
            cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)

            self.status_update.emit("Camera opened — processing...")

            frame_count = 0
            t_last = time.perf_counter()
            face_fps = 0.0
            swap_fps = 0.0
            t_swap_last = time.perf_counter()
            det_skip_counter = 0
            last_faces: List[dict] = []
            last_swapped: Optional[np.ndarray] = None
            total_frames = 0
            failed_reads = 0

            while self._running:
                ret, frame_raw = cap.read()
                if not ret:
                    failed_reads += 1
                    if failed_reads > 30:
                        log.error("Camera read failed 30 times, stopping")
                        break
                    time.sleep(0.01)
                    continue
                failed_reads = 0
                frame_count += 1
                total_frames += 1
                h, w = frame_raw.shape[:2]

                # Resize for display
                if abs(self.resize - 1.0) > 0.01:
                    display = cv2.resize(frame_raw,
                                         (int(w * self.resize), int(h * self.resize)))
                else:
                    display = frame_raw.copy()

                result = display.copy()

                # Detection (throttled)
                det_skip_counter += 1
                if det_skip_counter > self.frame_skip:
                    det_skip_counter = 0
                    if self.engine:
                        t_detect = time.perf_counter()
                        last_faces = self.engine.detect_faces(
                            display, threshold=self.threshold)
                        detect_ms = (time.perf_counter() - t_detect) * 1000
                        t_swap_last = time.perf_counter()
                        self.faces_detected.emit(last_faces, self._selected_face_idx)

                # Swap
                with self._lock:
                    src_emb = self.source_embedding
                if src_emb is not None and last_faces:
                    target_idx = min(self._selected_face_idx, len(last_faces) - 1)
                    if target_idx >= 0:
                        try:
                            result = self.engine.swap_face(
                                src_emb, last_faces[target_idx], result,
                                model_name=self.model,
                                pixel_boost=self.pixel_boost,
                                weight=self.weight,
                            )
                            t_now = time.perf_counter()
                            swap_fps = 1.0 / max(t_now - t_swap_last, 1e-6)
                            t_swap_last = t_now
                        except Exception as e:
                            log.error("Swap error: %s", traceback.format_exc())
                            self.error_occurred.emit(f"Swap error: {e}")

                # FPS
                t_now = time.perf_counter()
                if t_now - t_last >= 1.0:
                    face_fps = frame_count / (t_now - t_last)
                    frame_count = 0
                    t_last = t_now

                fps_text = f"FPS:{face_fps:.0f}  SWAP:{swap_fps:.0f}  FACE:{len(last_faces)}"
                stats_text = f"{self.model}  PB:{self.pixel_boost}"

                # ── Post-processing filters ──
                filtered = self._apply_post_filters(result, display)

                # Store for vcam / bestcam / recording
                with self._lock:
                    self._current_frame = filtered.copy()
                    if self.recorder and self.recorder.recording:
                        self.recorder.write_frame(filtered)
                    if self.vcam and self.vcam.running:
                        self.vcam.send_frame(filtered)
                    if self.bestcam and self.bestcam.connected:
                        self.bestcam.send(filtered)

                # Emit: input (display) + output (filtered)
                self.frame_ready.emit(display, filtered)
                self.stats_update.emit(fps_text, stats_text)

            log.info("Loop ended: %d frames", total_frames)

        except Exception as e:
            log.error("Processing error: %s\n%s", e, traceback.format_exc())
            self.error_occurred.emit(f"Processing error: {e}")
        finally:
            if cap:
                cap.release()
            self._running = False


class MainWindow(QMainWindow):
    """PixelMorph main application window."""

    def __init__(self):
        super().__init__()
        log.info("=== MainWindow init ===")

        try:
            # Core backend
            self.settings = SettingsManager()
            self.engine = FaceEngine()
            self.vcam = VirtualCameraOutput()
            self.bestcam = BestCamBridge()
            self.recorder = Recorder()
            self.processing = ProcessingThread(self)

            # State
            self._source_image: Optional[np.ndarray] = None
            self._source_face_thumb: Optional[np.ndarray] = None
            self._source_faces: List[dict] = []
            self._selected_source_idx: int = 0
            self._source_embedding: Optional[np.ndarray] = None
            self._is_running: bool = False
            self._recording: bool = False
            self._recordings_dir = str(Path.home() / "Videos" / "PixelMorph")

            # Build UI
            self._build_ui()
            self.control_panel.set_models(self.engine.available_models)
            self._connect_signals()
            self._load_settings()

            # UI timer (keeps previews responsive)
            self._update_timer = QTimer(self)
            self._update_timer.timeout.connect(self._tick)
            self._update_timer.start(16)

            self._latest_input: Optional[np.ndarray] = None
            self._latest_output: Optional[np.ndarray] = None

            log.info("MainWindow ready")
        except Exception as e:
            log.critical("MainWindow init failed: %s", traceback.format_exc())
            raise

    # ── UI Build ────────────────────────────────────

    def _build_ui(self):
        self.setWindowTitle("PixelMorph — Face Swap")
        self.setMinimumSize(1100, 700)

        geom = self.settings.get("window_geometry")
        if geom and len(geom) == 4:
            self.setGeometry(*geom)
        else:
            self.resize(1400, 900)
            self.move(100, 100)

        central = QWidget()
        self.setCentralWidget(central)
        central.setObjectName("centralWidget")

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setChildrenCollapsible(False)

        # LEFT + CENTER: side-by-side previews
        self.preview_panel = SideBySidePanel()
        splitter.addWidget(self.preview_panel)

        # RIGHT: control panel
        self.control_panel = ControlPanel()
        splitter.addWidget(self.control_panel)

        splitter.setSizes([900, 350])
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(splitter)

    def _connect_signals(self):
        # Control panel → main window
        self.control_panel.source_requested.connect(self._on_load_source)
        self.control_panel.start_stop_requested.connect(self._on_start_stop)
        self.control_panel.recording_toggled.connect(self._on_rec_toggle)
        self.control_panel.snapshot_requested.connect(self._on_snapshot)
        self.control_panel.settings_changed.connect(self._on_setting_change)

        # INPUT preview → select target face in camera
        self.preview_panel.input_preview.face_clicked.connect(
            self._on_target_face_clicked)

        # Processing thread → UI
        self.processing.frame_ready.connect(self._on_frame_ready)
        self.processing.faces_detected.connect(self._on_faces_detected)
        self.processing.status_update.connect(self.control_panel.set_status)
        self.processing.stats_update.connect(self._on_stats_update)
        self.processing.error_occurred.connect(self._on_error)

    # ── Settings ────────────────────────────────────

    def _load_settings(self):
        self.control_panel.load_settings(self.settings.all)

        last_source = self.settings.get("last_source_path", "")
        if last_source and os.path.exists(last_source):
            self._load_source_file(last_source)

        self._selected_source_idx = self.settings.get("selected_face_index", 0)
        self.preview_panel.input_preview._show_fps = (
            self.settings.get("show_fps", True))

    def _save_settings(self):
        geo = self.geometry()
        d = {
            "window_geometry": [geo.x(), geo.y(), geo.width(), geo.height()],
            "model": self.control_panel.get_setting("model"),
            "pixel_boost": self.control_panel.get_setting("pixel_boost"),
            "camera_device": self.control_panel.get_setting("camera_device"),
            "camera_device_name": self.control_panel.get_camera_device_name(),
            "frame_skip": self.control_panel.get_setting("frame_skip"),
            "weight": self.control_panel.get_setting("weight"),
            "resize": self.control_panel.get_setting("resize"),
            "threshold": self.control_panel.get_setting("threshold"),
            "clahe": self.control_panel.get_setting("clahe"),
            "sharpen": self.control_panel.get_setting("sharpen"),
            "white_balance": self.control_panel.get_setting("white_balance"),
            "color_match": self.control_panel.get_setting("color_match"),
            "show_landmarks": self.control_panel.get_setting("show_landmarks"),
            "show_fps": self.control_panel.get_setting("show_fps"),
            "show_stats": self.control_panel.get_setting("show_stats"),
            "selected_face_index": self._selected_source_idx,
        }
        self.settings.set_many(d)

    # ── Timer ───────────────────────────────────────

    def _tick(self):
        pass  # frame updates happen via signals, no polling needed

    # ── Frame Handling ──────────────────────────────

    def _on_frame_ready(self, input_frame: np.ndarray,
                        output_frame: np.ndarray):
        """INPUT panel ← camera feed | OUTPUT panel ← swap result."""
        self.preview_panel.input_preview.set_frame(input_frame)
        self.preview_panel.output_preview.set_frame(output_frame)
        self._latest_input = input_frame
        self._latest_output = output_frame

    def _on_faces_detected(self, faces: list, selected_idx: int):
        """Detection overlays go to INPUT panel only."""
        self.preview_panel.input_preview.set_faces(faces)
        self.preview_panel.input_preview.set_selected_face(selected_idx)
        self.control_panel.set_faces_count(len(faces), selected_idx)

    def _on_stats_update(self, fps_text: str, stats_text: str):
        """Stats overlay goes to INPUT panel only."""
        self.preview_panel.input_preview.set_fps_text(fps_text)
        self.preview_panel.input_preview.set_stats_text(stats_text)

    def _on_error(self, msg: str):
        self.control_panel.set_status(f"⚠ {msg}")

    def _on_target_face_clicked(self, index: int):
        """User clicked a face in the INPUT panel → choose target to swap."""
        log.info("Target face #%d selected", index)
        self.processing._selected_face_idx = index
        self.preview_panel.input_preview.set_selected_face(index)
        self.control_panel.set_status(f"Swapping face #{index}")

    # ── Source Face Loading ─────────────────────────

    def _on_load_source(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Source Face Image", "",
            "Images (*.jpg *.jpeg *.png *.bmp *.webp)")
        if path:
            self._load_source_file(path)

    def _load_source_file(self, path: str):
        img = cv2.imread(path)
        if img is None:
            QMessageBox.warning(self, "Error", f"Cannot load: {path}")
            return

        self._source_image = img
        threshold = self.control_panel.get_setting("threshold") or 0.35
        faces = self.engine.detect_faces(img, threshold=threshold)
        if not faces:
            QMessageBox.warning(self, "No Face",
                                "No face detected in source image.")
            return

        self._source_faces = faces
        self.control_panel.set_source_path(path)

        if len(faces) > 1:
            dialog = FaceSelectorDialog(img, faces, self)
            dialog.face_selected.connect(self._on_source_face_selected)
            dialog.exec()
        else:
            self._on_source_face_selected(0, faces[0])

    def _on_source_face_selected(self, index: int, face: dict):
        self._selected_source_idx = index
        model_name = self.control_panel.get_setting("model") or "hyperswap_1a_256"
        self._source_embedding = self.engine.prepare_embedding(face, model_name)

        # Extract face thumbnail for control panel display
        if self._source_image is not None:
            x1, y1, x2, y2 = [int(v) for v in face["bbox"]]
            thumb = self._source_image[y1:y2, x1:x2]
            if thumb.size > 0:
                self._source_face_thumb = thumb
                self.control_panel.set_source_thumbnail(thumb)

        self.processing.set_source_embedding(self._source_embedding)
        self.control_panel.set_faces_count(len(self._source_faces), index)
        self.control_panel.set_status(
            f"Source face #{index} ready ({face['score']:.2f})")

    # ── Start / Stop ────────────────────────────────

    def _on_start_stop(self):
        if not self._is_running:
            self._start_processing()
        else:
            self._stop_processing()

    def _start_processing(self):
        if self._source_embedding is None:
            QMessageBox.information(self, "No Source",
                                    "Load a source face image first.")
            self.control_panel.set_running(False)
            return

        # Configure processing
        self.processing.source_embedding = self._source_embedding
        self.processing.camera_device = (
            self.control_panel.get_setting("camera_device") or 0)
        self.processing.model = (
            self.control_panel.get_setting("model") or "hyperswap_1a_256")
        self.processing.pixel_boost = (
            self.control_panel.get_setting("pixel_boost") or 512)
        self.processing.threshold = (
            self.control_panel.get_setting("threshold") or 0.35)
        self.processing.weight = (
            self.control_panel.get_setting("weight") if
            self.control_panel.get_setting("weight") is not None else 0.5)
        self.processing.resize = (
            self.control_panel.get_setting("resize") if
            self.control_panel.get_setting("resize") is not None else 0.75)

        # Start virtual camera — appears as "PixelMorph" (or "OBS Virtual Camera") in all apps
        if self.vcam.available:
            self.vcam.configure(width=1280, height=720, fps=30)
            ok = self.vcam.start()
            if ok:
                dev = self.vcam.device_name
                self.control_panel.set_status(f"▶ Active  |  VCam: {dev}")
            else:
                log.warning("Virtual camera failed to start: %s", self.vcam.error)
                self.control_panel.set_status(f"⚠ VCam error: {self.vcam.error}")
        else:
            log.warning("Virtual camera not available: %s", self.vcam.error)
            self.control_panel.set_status("⚠ No virtual camera driver")

        # Connect BestCam (watermark-free virtual camera for Snap Camera)
        bestcam_ok = self.bestcam.connect()
        if bestcam_ok:
            log.info("BestCam virtual camera connected")
            self.control_panel.set_status("▶ Active  |  BestCam ready")
        else:
            log.info("BestCam not available (Snap Camera will use e2eSoft VCam)")

        # GO
        self.processing.start(self.engine, self.vcam, self.bestcam, self.recorder)
        self._is_running = True
        self.control_panel.set_status("▶ Processing active")
        log.info("Processing started")

    def _stop_processing(self):
        self.processing.stop()
        if self.vcam.running:
            self.vcam.stop()
        if self.bestcam.connected:
            self.bestcam.disconnect()
            log.info("BestCam disconnected")
        if self.recorder.recording:
            path = self.recorder.stop()
            if path:
                self.control_panel.set_status(f"⏹ Saved: {path}")
        self._is_running = False
        self._recording = False
        self.control_panel.set_status("⏹ Stopped")
        self.preview_panel.input_preview.set_faces([])
        # Clear frames
        self.preview_panel.input_preview.set_frame(None)
        self.preview_panel.output_preview.set_frame(None)

    # ── Recording ──────────────────────────────────

    def _on_rec_toggle(self, active: bool):
        if not self._is_running:
            return
        if active:
            # Size the writer to the *actual* output frames, or REC silently dies
            frame = self.processing.get_current_frame()
            if frame is not None:
                h, w = frame.shape[:2]
            else:
                w = self.processing.cam_width or 1280
                h = self.processing.cam_height or 720
            fmt = (self.control_panel.get_setting("recording_format")
                   or "mp4").lower()
            self.recorder.configure(width=w, height=h,
                                    fps=self.settings.get("vcam_fps", 30),
                                    fmt=fmt)
            ok = self.recorder.start(output_dir=self._recordings_dir)
            if ok:
                self.control_panel.set_status("⏺ Recording...")
            else:
                self.control_panel.set_status("⚠ Recording failed")
                self.control_panel.set_recording_state(False)
        else:
            path = self.recorder.stop()
            if path:
                self.control_panel.set_status(f"⏹ Saved: {path}")
            else:
                self.control_panel.set_status("⏹ Recording stopped")

    # ── Snapshot ───────────────────────────────────

    def _on_snapshot(self):
        """Save the current output frame as a PNG screenshot."""
        if self._latest_output is None:
            self.control_panel.set_status("⚠ No frame to capture")
            return

        os.makedirs(self._recordings_dir, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        filename = f"snapshot_{ts}.png"
        filepath = os.path.join(self._recordings_dir, filename)

        try:
            cv2.imwrite(filepath, self._latest_output)
            log.info("Snapshot saved: %s", filepath)
            self.control_panel.set_status(f"📷 Snapshot: {filename}")
        except Exception as e:
            log.error("Snapshot save failed: %s", e)
            self.control_panel.set_status(f"⚠ Snapshot failed: {e}")

    # ── Settings Changes ───────────────────────────

    def _on_setting_change(self, key: str, value):
        self.settings.set(key, value)
        if key == "model":
            self.processing.model = value
            if self._source_faces and self._selected_source_idx < len(self._source_faces):
                self._source_embedding = self.engine.prepare_embedding(
                    self._source_faces[self._selected_source_idx], value)
                self.processing.set_source_embedding(self._source_embedding)
        elif key == "pixel_boost":
            self.processing.pixel_boost = value
        elif key == "weight":
            self.processing.weight = value
        elif key == "resize":
            self.processing.resize = value
        elif key == "frame_skip":
            self.processing.frame_skip = value
        elif key == "threshold":
            self.processing.threshold = value
        elif key == "camera_device":
            self.processing.camera_device = value
        elif key == "camera_width":
            self.processing.cam_width = value
        elif key == "camera_height":
            self.processing.cam_height = value
        elif key == "show_landmarks":
            self.preview_panel.input_preview.set_show_landmarks(value)
        elif key == "show_fps":
            self.preview_panel.input_preview.set_show_fps(value)
        elif key == "clahe":
            self.processing.clahe = bool(value)
        elif key == "sharpen":
            self.processing.sharpen = bool(value)
        elif key == "white_balance":
            self.processing.white_balance = bool(value)
        elif key == "color_match":
            self.processing.color_match = bool(value)

    # ── Close ──────────────────────────────────────

    def closeEvent(self, event: QCloseEvent):
        log.info("Window closing")
        if self._is_running:
            self._stop_processing()
        # Shut down ALL backends including MF Virtual Camera
        try:
            self.vcam.shutdown()
        except Exception as e:
            log.warning("VCam shutdown error: %s", e)
        try:
            if self.bestcam.connected:
                self.bestcam.disconnect()
        except Exception as e:
            log.warning("BestCam shutdown error: %s", e)
        self._save_settings()
        log.info("=== PixelMorph shutdown ===")
        event.accept()
