"""JSON-based settings persistence for PixelMorph."""

import json
import logging
import os
import traceback
from pathlib import Path
from typing import Any, Dict
from app.logger import get_logger

log = get_logger(__name__)


SETTINGS_PATH = Path(os.path.expanduser("~")) / ".pixelmorph" / "settings.json"


DEFAULT_SETTINGS: Dict[str, Any] = {
    # Window
    "window_x": 100,
    "window_y": 100,
    "window_width": 1400,
    "window_height": 900,
    # Camera
    "camera_device": 0,
    "camera_width": 1280,
    "camera_height": 720,
    # Model
    "model": "hyperswap_1a_256",
    "pixel_boost": 512,
    "threshold": 0.35,
    "weight": 0.5,
    "resize": 0.75,
    "frame_skip": 2,
    # Face
    "last_source_path": "",
    "selected_face_index": 0,
    # Output
    "output_mode": "window",  # window | virtual_cam | record | all
    "recording_format": "mp4",
    "recording_fps": 30,
    # Virtual camera
    "vcam_backend": "obs",  # obs | dshow
    "vcam_width": 1280,
    "vcam_height": 720,
    "vcam_fps": 30,
    # UI
    "show_landmarks": False,
    "show_fps": True,
    "show_stats": True,
    "compare_mode": False,
    # Batch
    "last_batch_folder": "",
    "last_video_path": "",
}


class SettingsManager:
    """Persists app settings to ~/.pixelmorph/settings.json."""

    def __init__(self):
        self._data: Dict[str, Any] = DEFAULT_SETTINGS.copy()
        log.debug("SettingsManager initialized, path=%s", SETTINGS_PATH)
        self._load()

    def _load(self) -> None:
        try:
            if SETTINGS_PATH.exists():
                with open(SETTINGS_PATH, "r") as f:
                    loaded = json.load(f)
                self._data = {**DEFAULT_SETTINGS, **loaded}
                log.info("Settings loaded from %s (%d keys)", SETTINGS_PATH, len(loaded))
            else:
                log.debug("No settings file at %s, using defaults", SETTINGS_PATH)
        except Exception as e:
            log.warning("Corrupted settings file, starting fresh: %s", e)

    def save(self) -> None:
        try:
            SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(SETTINGS_PATH, "w") as f:
                json.dump(self._data, f, indent=2)
            log.debug("Settings saved to %s", SETTINGS_PATH)
        except Exception as e:
            log.error("Failed to save settings: %s", traceback.format_exc())

    def get(self, key: str, default: Any = None) -> Any:
        val = self._data.get(key, default)
        log.log(logging.DEBUG - 1 if hasattr(logging, 'DEBUG') else 5,
                "Settings get(%s) = %s", key, val)
        return val

    def set(self, key: str, value: Any) -> None:
        old = self._data.get(key)
        self._data[key] = value
        if old != value:
            log.info("Settings changed: %s = %s (was %s)", key, value, old)
        self.save()

    def set_many(self, pairs: Dict[str, Any]) -> None:
        for k, v in pairs.items():
            old = self._data.get(k)
            if old != v:
                log.info("Settings changed: %s = %s (was %s)", k, v, old)
        self._data.update(pairs)
        self.save()

    @property
    def all(self) -> Dict[str, Any]:
        return self._data.copy()
