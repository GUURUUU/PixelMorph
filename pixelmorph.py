#!/usr/bin/env python3
"""
PixelMorph — Advanced face swap application with holographic GUI.

Usage:
    python pixelmorph.py

Features:
    - Image-to-image face swap
    - Live webcam face swap
    - Virtual camera output (OBS / DirectShow)
    - Video recording with audio passthrough
    - Batch processing (folder / video file)
    - Full control panel with real-time adjustments
    - Holographic neon theme
"""

import sys
import os
import traceback

# Ensure the app directory is on the path
_app_dir = os.path.dirname(os.path.abspath(__file__))
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from app.logger import setup_logging, get_logger
from app.styles import apply_theme
from app.main_window import MainWindow

log = get_logger(__name__)


def main():
    # Initialize logging first
    setup_logging()
    log.info("=== PixelMorph %s starting ===", "1.0.0")
    log.debug("Python %s | PyQt6 | OpenCV | onnxruntime-gpu", sys.version)

    try:
        # High-DPI support
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

        app = QApplication(sys.argv)
        app.setApplicationName("PixelMorph")
        app.setOrganizationName("PixelMorph")
        log.debug("QApplication created")

        # Apply holographic theme
        apply_theme(app)
        log.debug("Holographic theme applied")

        # Create and show main window
        window = MainWindow()
        window.show()
        log.info("Main window displayed successfully")

    except Exception as e:
        log.critical("Fatal error during startup: %s", traceback.format_exc())
        sys.exit(1)

    # Global exception hook for unhandled Qt exceptions
    def excepthook(exc_type, exc_value, exc_tb):
        log.error("Unhandled exception: %s",
                  "".join(traceback.format_exception(exc_type, exc_value, exc_tb)))

    sys.excepthook = excepthook

    log.info("Entering Qt event loop")
    exit_code = app.exec()
    log.info("Event loop exited with code %d", exit_code)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
