"""
Video recorder with optional audio passthrough for PixelMorph.
"""

import os
import subprocess
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

import cv2
import numpy as np
from app.logger import get_logger

log = get_logger(__name__)


class Recorder:
    """
    Records swapped video output to a file.

    Audio passthrough: uses ffmpeg to mux audio with recorded video.
    If ffmpeg is not available, records video-only.
    """

    def __init__(self):
        self._writer: Optional[cv2.VideoWriter] = None
        self._recording = False
        self._thread: Optional[threading.Thread] = None
        self._frame_callback: Optional[Callable] = None
        self._output_path: Optional[str] = None
        self._width = 0
        self._height = 0
        self._fps = 30
        self._format = "mp4"
        self._has_ffmpeg = self._check_ffmpeg()
        self._audio_thread: Optional[threading.Thread] = None
        self._audio_running = False
        self._frame_queue: list = []
        self._max_queue = 30
        self._audio_temp: Optional[str] = None
        log.debug("Recorder created (ffmpeg=%s)", self._has_ffmpeg)

    @staticmethod
    def _check_ffmpeg() -> bool:
        """Check if ffmpeg is available in PATH."""
        try:
            result = subprocess.run(["ffmpeg", "-version"],
                                   capture_output=True, timeout=2)
            available = result.returncode == 0
            if available:
                log.debug("ffmpeg found: %s", result.stdout.decode()[:80])
            else:
                log.debug("ffmpeg check returned code %d", result.returncode)
            return available
        except FileNotFoundError:
            log.debug("ffmpeg not found in PATH")
            return False
        except Exception as e:
            log.debug("ffmpeg check exception: %s", e)
            return False

    @property
    def recording(self) -> bool:
        return self._recording

    @property
    def has_ffmpeg(self) -> bool:
        return self._has_ffmpeg

    def configure(self, width: int, height: int, fps: int = 30,
                  fmt: str = "mp4"):
        log.debug("Recorder configure: %dx%d @%d fps, format=%s", width, height, fps, fmt)
        self._width = width
        self._height = height
        self._fps = fps
        self._format = fmt

    def start(self, output_dir: Optional[str] = None) -> bool:
        """Start recording. Returns True if successful."""
        if self._recording:
            log.warning("Already recording, ignoring start")
            return False

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = output_dir or str(Path.home() / "Videos" / "PixelMorph")
        Path(out_dir).mkdir(parents=True, exist_ok=True)

        ext = self._format.lower()
        self._output_path = os.path.join(out_dir, f"pixelmorph_{timestamp}.{ext}")

        fourcc_map = {
            "mp4": cv2.VideoWriter_fourcc(*"mp4v"),
            "avi": cv2.VideoWriter_fourcc(*"XVID"),
            "mkv": cv2.VideoWriter_fourcc(*"X264"),
        }
        fourcc = fourcc_map.get(self._format, cv2.VideoWriter_fourcc(*"mp4v"))

        self._writer = cv2.VideoWriter(self._output_path, fourcc,
                                        self._fps,
                                        (self._width, self._height))
        if not self._writer.isOpened():
            log.error("Failed to open VideoWriter for %s", self._output_path)
            self._writer = None
            self._output_path = None
            return False

        self._recording = True
        self._frame_queue = []
        self._audio_running = True

        # Start audio capture thread
        if self._has_ffmpeg:
            self._audio_thread = threading.Thread(
                target=self._capture_audio, daemon=True, name="audio-capture")
            self._audio_thread.start()
            log.debug("Audio capture thread started")

        log.info("Recording started: %s (%dx%d, %s, %dfps)",
                 self._output_path, self._width, self._height, self._format, self._fps)
        return True

    def stop(self) -> Optional[str]:
        """Stop recording and finalize. Returns output path or None."""
        if not self._recording:
            return None

        log.info("Stopping recording...")
        self._recording = False
        self._audio_running = False
        frame_count = len(self._frame_queue)

        if self._audio_thread:
            self._audio_thread.join(timeout=3.0)
            if self._audio_thread.is_alive():
                log.warning("Audio thread did not stop cleanly")
            self._audio_thread = None

        path = self._output_path

        if self._writer:
            self._writer.release()
            self._writer = None
            log.debug("VideoWriter released")

        # Mux audio if available
        if self._has_ffmpeg and self._audio_temp and os.path.exists(self._audio_temp):
            try:
                final_path = path.replace(f".{self._format}", f"_with_audio.{self._format}")
                cmd = [
                    "ffmpeg", "-y",
                    "-i", path,
                    "-i", self._audio_temp,
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-shortest",
                    final_path
                ]
                log.debug("Muxing audio: %s", " ".join(cmd))
                result = subprocess.run(cmd, capture_output=True, timeout=30)
                if result.returncode == 0:
                    # Replace original with muxed version
                    os.replace(final_path, path)
                    log.info("Audio muxed successfully")
                else:
                    log.warning("Audio mux failed (stderr): %s",
                               result.stderr.decode()[:200])
            except Exception as e:
                log.warning("Audio mux exception: %s", e)
            finally:
                try:
                    os.unlink(self._audio_temp)
                except Exception:
                    pass

        self._output_path = None
        self._audio_temp = None
        log.info("Recording stopped: %d frames, saved to %s", frame_count, path)
        return path

    def write_frame(self, frame: np.ndarray):
        """Write a single frame to the recording."""
        if not self._recording or self._writer is None:
            return

        h, w = frame.shape[:2]
        if w != self._width or h != self._height:
            frame = cv2.resize(frame, (self._width, self._height))

        self._writer.write(frame)

        if len(self._frame_queue) < self._max_queue:
            self._frame_queue.append(time.time())

    def _capture_audio(self):
        """Background audio capture for passthrough."""
        import pyaudio
        import wave
        import tempfile

        try:
            self._audio_temp = tempfile.NamedTemporaryFile(
                suffix=".wav", delete=False).name
            log.debug("Audio capture to %s", self._audio_temp)

            CHUNK = 1024
            FORMAT = pyaudio.paInt16
            CHANNELS = 1
            RATE = 16000

            p = pyaudio.PyAudio()
            stream = p.open(format=FORMAT,
                           channels=CHANNELS,
                           rate=RATE,
                           input=True,
                           frames_per_buffer=CHUNK)

            wf = wave.open(self._audio_temp, 'wb')
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(p.get_sample_size(FORMAT))
            wf.setframerate(RATE)

            frames_captured = 0
            while self._audio_running:
                data = stream.read(CHUNK, exception_on_overflow=False)
                wf.writeframes(data)
                frames_captured += 1

            wf.close()
            stream.stop_stream()
            stream.close()
            p.terminate()
            log.debug("Audio captured: %d frames", frames_captured)

        except Exception as e:
            log.warning("Audio capture stopped: %s", traceback.format_exc())
