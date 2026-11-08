"""
BestCam bridge — sends PixelMorph frames to BestCam virtual camera.

BestCam is a watermark-free Windows 11 virtual camera that uses
MFCreateVirtualCamera. Frames are passed via shared memory (NV12 format).

Shared memory layout (24-byte header + NV12 frame):
  Offset   Size  Field
  0        4     width (uint32)
  4        4     height (uint32)
  8        4     stride (uint32, usually = width)
  12       4     frame_size (uint32, = width * height * 3/2)
  16       8     frame_index (uint64)
  24       ...   NV12 pixel data

Usage:
    bridge = BestCamBridge()
    bridge.connect()                    # waits for shared mem up to 30s
    bridge.send(frame_bgr)              # BGR numpy array (h,w,3)
    # or
    bridge.start_streaming(frame_gen)   # continuous streaming in thread
    bridge.stop_streaming()
"""

import cv2
import ctypes
import ctypes.wintypes
import logging
import struct
import threading
import time
from typing import Callable, Iterator, Optional

import numpy as np

log = logging.getLogger(__name__)

SHARED_MEM_NAME = "Global\\BestCam_SharedMem"
MUTEX_NAME = "Global\\BestCam_Mutex"
HEADER_SIZE = 24  # 4 uint32 + 1 uint64
FILE_MAP_READ = 0x0004
FILE_MAP_WRITE = 0x0002
MUTEX_TIMEOUT_MS = 5

# Win32 constants
WAIT_OBJECT_0 = 0
WAIT_ABANDONED = 0x00000080
WAIT_TIMEOUT = 0x00000102
INFINITE = 0xFFFFFFFF


class BestCamBridge:
    """Push frames to BestCam virtual camera via shared memory."""

    def __init__(self, width: int = 1920, height: int = 1080, fps: int = 30):
        self._width = width
        self._height = height
        self._fps = fps
        self._frame_size = width * height * 3 // 2
        self._total_size = HEADER_SIZE + self._frame_size

        self._k32 = ctypes.WinDLL("kernel32", use_last_error=True)

        # Set proper 64-bit return types
        self._k32.OpenFileMappingW.restype = ctypes.c_void_p
        self._k32.OpenFileMappingW.argtypes = [
            ctypes.wintypes.DWORD, ctypes.wintypes.BOOL, ctypes.wintypes.LPCWSTR
        ]
        self._k32.MapViewOfFile.restype = ctypes.c_void_p
        self._k32.MapViewOfFile.argtypes = [
            ctypes.c_void_p, ctypes.wintypes.DWORD,
            ctypes.wintypes.DWORD, ctypes.wintypes.DWORD, ctypes.c_size_t
        ]
        self._k32.UnmapViewOfFile.restype = ctypes.wintypes.BOOL
        self._k32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
        self._k32.CloseHandle.restype = ctypes.wintypes.BOOL
        self._k32.CloseHandle.argtypes = [ctypes.c_void_p]

        # Mutex functions
        self._k32.OpenMutexW.restype = ctypes.c_void_p
        self._k32.OpenMutexW.argtypes = [
            ctypes.wintypes.DWORD, ctypes.wintypes.BOOL, ctypes.wintypes.LPCWSTR
        ]
        self._k32.ReleaseMutex.restype = ctypes.wintypes.BOOL
        self._k32.ReleaseMutex.argtypes = [ctypes.c_void_p]
        self._k32.WaitForSingleObject.restype = ctypes.wintypes.DWORD
        self._k32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.wintypes.DWORD]

        self._h_map: Optional[int] = None
        self._h_mutex: Optional[int] = None
        self._ptr: Optional[int] = None
        self._frame_index = 0
        self._connected = False

        # Streaming thread
        self._stream_thread: Optional[threading.Thread] = None
        self._stream_stop = threading.Event()

        # Build static header bytes (width, height, stride, frame_size)
        self._header_static = struct.pack("<4I", width, height, width, self._frame_size)

    # ── Connection ──

    def connect(self) -> bool:
        """Open BestCam shared memory and mutex (retry up to 30s)."""
        for attempt in range(30):
            self._h_map = self._k32.OpenFileMappingW(
                FILE_MAP_WRITE | FILE_MAP_READ,
                False,
                SHARED_MEM_NAME,
            )
            if self._h_map:
                break
            if attempt == 0:
                log.info("Waiting for BestCam shared memory...")
            time.sleep(1)

        if not self._h_map:
            log.warning("BestCam shared memory not found after 30s. Is BestCamHost.exe running?")
            return False

        self._ptr = self._k32.MapViewOfFile(
            self._h_map,
            FILE_MAP_WRITE | FILE_MAP_READ,
            0, 0,
            0,  # map entire file
        )
        if not self._ptr:
            err = ctypes.get_last_error()
            log.warning("Failed to map BestCam shared memory (err=%d)", err)
            self._k32.CloseHandle(self._h_map)
            self._h_map = None
            return False

        # Open the cross-process mutex (SYNCHRONIZE | MUTEX_MODIFY_STATE)
        self._h_mutex = self._k32.OpenMutexW(0x001F0001, False, MUTEX_NAME)
        if not self._h_mutex:
            log.warning("Could not open BestCam mutex (non-fatal)")

        self._connected = True
        log.info(
            "BestCam bridge connected (%dx%d NV12, %.1f fps)",
            self._width, self._height, self._fps,
        )
        return True

    def disconnect(self):
        """Close shared memory and mutex handles."""
        self._connected = False
        self.stop_streaming()
        if self._ptr:
            self._k32.UnmapViewOfFile(ctypes.c_void_p(self._ptr))
            self._ptr = None
        if self._h_map:
            self._k32.CloseHandle(self._h_map)
            self._h_map = None
        if self._h_mutex:
            self._k32.CloseHandle(self._h_mutex)
            self._h_mutex = None

    @property
    def connected(self) -> bool:
        return self._connected

    # ── Mutex helpers ──

    def _acquire_mutex(self) -> bool:
        """Acquire the cross-process mutex. Returns True if owned."""
        if not self._h_mutex:
            return True  # no mutex = proceed without locking
        ret = self._k32.WaitForSingleObject(self._h_mutex, MUTEX_TIMEOUT_MS)
        return ret in (WAIT_OBJECT_0, WAIT_ABANDONED)

    def _release_mutex(self):
        """Release the cross-process mutex."""
        if self._h_mutex:
            self._k32.ReleaseMutex(self._h_mutex)

    # ── Send frame ──

    def send(self, frame_bgr: np.ndarray):
        """Convert BGR frame to NV12 and write to BestCam shared memory under mutex."""
        if not self._connected or self._ptr is None:
            return
        if frame_bgr is None or frame_bgr.size == 0:
            return

        # Resize if needed
        h, w = frame_bgr.shape[:2]
        if w != self._width or h != self._height:
            frame_bgr = cv2.resize(frame_bgr, (self._width, self._height),
                                   interpolation=cv2.INTER_LINEAR)

        # Convert BGR → NV12
        uv_offset = self._width * self._height
        nv12 = np.empty(self._frame_size, dtype=np.uint8)
        yuv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2YUV)
        nv12[:uv_offset] = yuv[:, :, 0].ravel()
        u_small = cv2.resize(yuv[:, :, 1], (self._width // 2, self._height // 2),
                             interpolation=cv2.INTER_LINEAR)
        v_small = cv2.resize(yuv[:, :, 2], (self._width // 2, self._height // 2),
                             interpolation=cv2.INTER_LINEAR)
        nv12[uv_offset::2] = u_small.ravel()
        nv12[uv_offset + 1::2] = v_small.ravel()

        # Build header with monotonic frame index
        header = self._header_static + struct.pack("<Q", self._frame_index)
        self._frame_index += 1

        # Write under mutex to avoid race with FrameServer's ZeroMemory/read
        got_mutex = self._acquire_mutex()
        try:
            ptr_int = int(ctypes.cast(self._ptr, ctypes.c_void_p).value
                          if hasattr(self._ptr, 'value') else self._ptr)
            ctypes.memmove(ctypes.c_void_p(ptr_int), header, HEADER_SIZE)
            ctypes.memmove(ctypes.c_void_p(ptr_int + HEADER_SIZE),
                           nv12.ctypes.data, self._frame_size)
        finally:
            if got_mutex:
                self._release_mutex()

    # ── Continuous streaming ──

    def start_streaming(self, frame_source: Callable[[], Optional[np.ndarray]]):
        """Start a background thread that sends frames at the configured fps.

        Args:
            frame_source: Callable that returns a BGR frame or None.
        """
        if self._stream_thread and self._stream_thread.is_alive():
            log.warning("Streaming already running")
            return

        self._stream_stop.clear()
        self._stream_thread = threading.Thread(
            target=self._stream_loop,
            args=(frame_source,),
            daemon=True,
        )
        self._stream_thread.start()
        log.info("BestCam streaming started at %d fps", self._fps)

    def stop_streaming(self):
        """Stop the background streaming thread."""
        self._stream_stop.set()
        if self._stream_thread and self._stream_thread.is_alive():
            self._stream_thread.join(timeout=2)
            self._stream_thread = None

    def _stream_loop(self, frame_source):
        """Background loop: grab frame → send → sleep."""
        interval = 1.0 / self._fps
        while not self._stream_stop.is_set():
            t0 = time.perf_counter()
            try:
                frame = frame_source()
                if frame is not None:
                    self.send(frame)
            except Exception as e:
                log.error("BestCam stream error: %s", e)
            elapsed = time.perf_counter() - t0
            sleep_time = interval - elapsed
            if sleep_time > 0:
                self._stream_stop.wait(sleep_time)

    def __del__(self):
        self.disconnect()
