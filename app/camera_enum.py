"""
Camera enumeration — get friendly names for DirectShow devices on Windows.

Uses pygrabber (pygrabber) to query the DirectShow filter graph,
returning (index, name, is_virtual) tuples so the UI can show proper labels
and avoid virtual cameras like Snap Camera or OBS Virtual Camera.
"""

from typing import List, Tuple
from app.logger import get_logger

log = get_logger(__name__)

# Substrings that indicate a virtual / capture-interception device
VIRTUAL_DEVICE_HINTS = [
    "snap", "obs", "virtual", "vcam", "droidcam", "ndi",
    "display capture", "screen capture", "mirror", "splitcam",
    "manycam", "streamlabs", "xsplit", "vban",
    "pixelmorph", "unity capture", "e2esoft", "iriun", "epoccam",
]


def _is_virtual(name: str) -> bool:
    """Heuristic: check if camera name looks like a virtual device."""
    lower = name.lower()
    for hint in VIRTUAL_DEVICE_HINTS:
        if hint in lower:
            return True
    return False


def enumerate_cameras() -> List[Tuple[int, str, bool]]:
    """
    Enumerate all DirectShow video input devices.

    Returns
    -------
    list of (index, friendly_name, is_virtual)
        Sorted so real cameras come before virtual ones.
    """
    devices: List[Tuple[int, str, bool]] = []
    try:
        from pygrabber.dshow_graph import FilterGraph
        graph = FilterGraph()
        names = graph.get_input_devices()
        for i, name in enumerate(names):
            is_virtual = _is_virtual(name)
            devices.append((i, name, is_virtual))
            log.debug("Camera %d: %s (virtual=%s)", i, name, is_virtual)
    except ImportError:
        log.warning("pygrabber not installed — falling back to OpenCV enumeration")
        import cv2
        for i in range(8):
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if cap.isOpened():
                devices.append((i, f"Camera {i}", False))
                cap.release()
    except Exception as e:
        log.error("Camera enumeration failed: %s", e)
        # Minimal fallback
        devices = [(i, f"Camera {i}", False) for i in range(4)]

    # Sort: real cameras first, then virtual
    devices.sort(key=lambda d: (1 if d[2] else 0, d[0]))
    log.info("Camera enumeration: %d device(s) found", len(devices))
    return devices


def find_best_camera(devices: List[Tuple[int, str, bool]] = None) -> int:
    """
    Pick the best camera index: prefer the first real (non-virtual) camera.
    Returns 0 if nothing reasonable found.
    """
    if devices is None:
        devices = enumerate_cameras()
    for idx, name, is_virtual in devices:
        if not is_virtual:
            log.info("Auto-selected camera %d: %s", idx, name)
            return idx
    if devices:
        fallback = devices[0][0]
        log.warning("No real camera found — falling back to camera %d: %s",
                     fallback, devices[0][1])
        return fallback
    log.warning("No cameras found at all, defaulting to 0")
    return 0
