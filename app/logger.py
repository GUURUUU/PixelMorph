"""
Centralized logging configuration for PixelMorph.
All modules use getLogger(__name__) — logs go to stderr with timestamps.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(level: int = logging.DEBUG) -> None:
    """
    Configure root logger. Call once from pixelmorph.py main().

    Logs to stderr with format:
        2026-07-23 05:30:00.123 [INFO] [module.name] Message text here
    Also writes to ~/.pixelmorph/pixelmorph.log for persistent review.
    """
    log_dir = Path.home() / ".pixelmorph"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "pixelmorph.log"

    formatter = logging.Formatter(
        fmt="%(asctime)s.%(msecs)03d [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler (stderr)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    # File handler (persistent, append mode)
    file_handler = RotatingFileHandler(
        str(log_file), maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    # Avoid duplicate handlers if setup is called twice
    if not root.handlers:
        root.addHandler(console_handler)
        root.addHandler(file_handler)

    logging.info("=== PixelMorph logging initialized ===")
    logging.info("Log file: %s", log_file)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name. Typically __name__ from the caller."""
    return logging.getLogger(name)
