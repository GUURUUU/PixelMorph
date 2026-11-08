"""
Tests for camera enumeration heuristics (no hardware needed).
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.camera_enum import VIRTUAL_DEVICE_HINTS, _is_virtual


def test_virtual_hints():
    assert _is_virtual("OBS Virtual Camera") is True
    assert _is_virtual("PixelMorph") is True
    assert _is_virtual("e2eSoft VCam") is True
    assert _is_virtual("DroidCam Video Source") is True
    assert _is_virtual("Snap Camera") is True
    assert _is_virtual("Iriun Webcam") is True
    assert _is_virtual("EpocCam") is True


def test_real_cameras():
    assert _is_virtual("USB2.0 HD UVC WebCam") is False
    assert _is_virtual("Logitech StreamCam") is False
    assert _is_virtual("Intel Integrated Camera") is False


def test_hint_list_sorted_sane():
    # every hint must be lowercase to keep _is_virtual deterministic
    assert all(h == h.lower() for h in VIRTUAL_DEVICE_HINTS)
