"""
Virtual camera output for PixelMorph.

Uses pyvirtualcam the exact same way as a simple webcam passthrough script:
    with pyvirtualcam.Camera(width, height, fps=30) as cam:
        cam.send(frame_rgb)
        cam.sleep_until_next_frame()

No backend specified â€” pyvirtualcam auto-detects what's available
(OBS Virtual Camera, Unity Capture, e2eSoft VCam driver, etc.).
Whatever device it creates is visible in all apps.

Lifecycle:
  1. App starts â†’ detect if pyvirtualcam works (test with 64x64)
  2. User clicks START â†’ pyvirtualcam starts â†’ device appears in ALL apps
  3. Processing loop calls send_frame() each frame
  4. User clicks STOP â†’ pyvirtualcam stops
  5. App exits â†’ pyvirtualcam cleaned up
"""

from typing import Optional

import numpy as np

from app.logger import get_logger

log = get_logger(__name__)


class VirtualCameraOutput:
    """
    Minimal pyvirtualcam wrapper. Matches the user's simple passthrough pattern.
    No backend selection â€” let pyvirtualcam auto-detect.
    """

    def __init__(self, backend: Optional[str] = None):
        self._cam = None
        self._running = False
        self._available = False
        self._error: Optional[str] = None
        self._device_name: str = "PixelMorph"
        self._backend: Optional[str] = backend  # force a backend, or None=auto

        self._width = 1280
        self._height = 720
        self._fps = 30

        log.debug("VirtualCameraOutput created")
        self._detect()

    # ── Detection ──

    def _detect(self):
        """
        Probe pyvirtualcam backends. If a backend was forced in __init__,
        only that one is tried. Otherwise auto-None first (pyvirtualcam
        picks OBS on Windows), then explicit obs, then unitycapture, dshow.
        """
        if self._backend:
            candidates: list = [self._backend]
        else:
            candidates = [None, "obs", "unitycapture", "dshow"]
        import pyvirtualcam

        for backend in candidates:
            try:
                test = pyvirtualcam.Camera(
                    width=64, height=64, fps=1,
                    backend=backend if backend else None)
                try:
                    self._device_name = test.device or "PixelMorph"
                finally:
                    test.close()
                self._available = True
                self._backend = backend
                label = backend or "auto"
                log.info("pyvirtualcam works via '%s' — device='%s'",
                         label, self._device_name)
                return
            except Exception as e:
                log.debug("backend '%s' unavailable: %s", backend, e)

        self._available = False
        self._error = (
            "No virtual camera driver usable. Install OBS (default) or run "
            "UnityCapture\\InstallCustomName.bat with device name 'PixelMorph'.")

    # â”€â”€ Properties â”€â”€

    @property
    def available(self) -> bool:
        return self._available

    @property
    def error(self) -> Optional[str]:
        return self._error

    @property
    def running(self) -> bool:
        return self._running

    @property
    def device_name(self) -> str:
        return self._device_name

    @property
    def backend(self) -> Optional[str]:
        """Backend actually in use (None = pyvirtualcam auto)."""
        return self._backend

    # â”€â”€ Public API â”€â”€

    def configure(self, width: int = 1280, height: int = 720, fps: int = 30):
        """Set resolution and frame rate (call before start())."""
        self._width = width
        self._height = height
        self._fps = fps
        log.debug("VCam configured: %dx%d @%d fps", width, height, fps)

    def start(self) -> bool:
        """Start pyvirtualcam. Returns True on success."""
        if self._running:
            return True

        if not self._available:
            log.warning("pyvirtualcam not available to start")
            return False

        try:
            import pyvirtualcam
            self._cam = pyvirtualcam.Camera(
                width=self._width,
                height=self._height,
                fps=self._fps,
                backend=self._backend,  # None → pyvirtualcam auto-detect
            )
            self._device_name = self._cam.device
            self._running = True
            log.info("pyvirtualcam started â€” device='%s'", self._device_name)
            return True
        except Exception as e:
            self._cam = None
            self._running = False
            self._error = str(e)
            log.warning("pyvirtualcam start failed: %s", e)
            return False

    def stop(self):
        """Stop pyvirtualcam."""
        if self._cam is not None:
            try:
                self._cam.close()
                log.debug("pyvirtualcam closed")
            except Exception as e:
                log.warning("Error closing pyvirtualcam: %s", e)
            self._cam = None
        self._running = False
        log.info("pyvirtualcam stopped")

    def shutdown(self):
        """Full shutdown â€” called on app exit."""
        log.info("Shutting down virtual camera...")
        self.stop()
        log.info("Virtual camera shut down")

    def send_frame(self, frame: np.ndarray):
        """
        Send a BGR frame to the virtual camera.
        Matches the user's script: convert BGRâ†’RGB, resize if needed, send.
        """
        if not self._running or self._cam is None:
            return
        if frame is None or frame.size == 0:
            return

        try:
            # BGR â†’ RGB (pyvirtualcam expects RGB)
            rgb = frame[:, :, ::-1].copy()

            # Resize to configured dimensions if needed
            if (rgb.shape[1] != self._width or
                    rgb.shape[0] != self._height):
                import cv2
                rgb = cv2.resize(rgb, (self._width, self._height),
                                 interpolation=cv2.INTER_LINEAR)

            self._cam.send(rgb)
        except Exception as e:
            log.warning("VCam send_frame error: %s", e)
