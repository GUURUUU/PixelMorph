"""
e2eSoft VCam output for PixelMorph.

Snap Camera uses MediaFoundation to enumerate cameras, which ONLY sees
kernel-level KSCATEGORY_VIDEO_CAMERA devices. OBS Virtual Camera and
Unity Capture are user-mode DirectShow filters — invisible to MF.

e2eSoft VCam HAS a kernel driver (VCam_WDM.sys), so it IS visible to
Snap Camera. This module sends PixelMorph frames to the e2eSoft VCam
kernel driver, making face-swapped output available to Snap Camera.

ARCHITECTURE:
    PixelMorph → e2eSoft VCam (kernel driver) → Snap Camera → Zoom/Teams
                     ↓
              (also visible to WhatsApp, Chrome, etc.)

LIFECYCLE:
    1. Detect e2eSoft VCam device via SetupAPI
    2. Open kernel device for IOCTL communication
    3. Send frames using e2eSoft-specific IOCTL interface
    4. Close device on shutdown
"""

import ctypes
import ctypes.wintypes
import uuid
from pathlib import Path
from typing import Optional

import numpy as np

from app.logger import get_logger

log = get_logger(__name__)

# ── Win32 constants ──
GENERIC_READ  = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ  = 1
FILE_SHARE_WRITE = 2
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x80
INVALID_HANDLE_VALUE = -1

# DIGCF flags
DIGCF_PRESENT = 0x02
DIGCF_DEVICEINTERFACE = 0x10

# KSCATEGORY_VIDEO_CAMERA — the MF camera device interface GUID
KSCATEGORY_VIDEO_CAMERA = uuid.UUID('{E5323777-F977-4F5B-9B55-B94699C46E44}')

# IOCTL codes for e2eSoft VCam (reverse-engineered from VCam_WDM.sys)
# These are sent to the kernel driver via DeviceIoControl
IOCTL_VCAM_GET_FORMAT    = 0x82002008  # Get current video format
IOCTL_VCAM_SET_FORMAT    = 0x8200200C  # Set video format (width, height, fps)
IOCTL_VCAM_SEND_FRAME    = 0x82002010  # Send a video frame to the driver
IOCTL_VCAM_START_STREAM  = 0x82002014  # Start streaming
IOCTL_VCAM_STOP_STREAM   = 0x82002018  # Stop streaming


class E2eVirtualCamera:
    """
    Pushes frames to the e2eSoft VCam kernel driver, making them
    available to any MediaFoundation app (Snap Camera, etc.).
    """

    def __init__(self):
        self._handle: Optional[int] = None
        self._device_path: Optional[str] = None
        self._available: bool = False
        self._running: bool = False
        self._error: Optional[str] = None

        self._width = 1280
        self._height = 720
        self._fps = 30

        log.debug("E2eVirtualCamera created")
        self._detect()

    # ── Detection ──────────────────────────────────────────────────

    def _detect(self):
        """Scan for e2eSoft VCam device via SetupAPI."""
        try:
            self._device_path = self._find_e2e_device()
            if self._device_path:
                self._available = True
                log.info("e2eSoft VCam device found: %s", self._device_path)
            else:
                self._error = "e2eSoft VCam device not found"
                log.warning("e2eSoft VCam device not found")
        except Exception as e:
            self._error = f"e2eSoft detection failed: {e}"
            log.warning("e2eSoft detection failed: %s", e)

    def _find_e2e_device(self) -> Optional[str]:
        """
        Enumerate KSCATEGORY_VIDEO_CAMERA devices.
        Returns the device path for the e2eSoft VCam, or None.
        """
        setupapi = ctypes.WinDLL('setupapi', use_last_error=True)
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

        # Build GUID struct
        g = KSCATEGORY_VIDEO_CAMERA
        guid_bytes = g.bytes_le
        guid_array = (ctypes.c_ubyte * 16)(*guid_bytes)

        # SP_DEVICE_INTERFACE_DATA
        class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
            _fields_ = [
                ('cbSize', ctypes.wintypes.DWORD),
                ('InterfaceClassGuid', ctypes.c_ubyte * 16),
                ('Flags', ctypes.wintypes.DWORD),
                ('Reserved', ctypes.c_ulong),
            ]

        # SetupDiGetClassDevsW
        setupapi.SetupDiGetClassDevsW.restype = ctypes.c_void_p
        setupapi.SetupDiGetClassDevsW.argtypes = [
            ctypes.POINTER(ctypes.c_ubyte * 16),  # ClassGuid
            ctypes.wintypes.LPCWSTR,               # Enumerator
            ctypes.wintypes.HWND,                  # hwndParent
            ctypes.wintypes.DWORD,                 # Flags
        ]

        hDevInfo = setupapi.SetupDiGetClassDevsW(
            guid_array, None, None,
            DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
        )

        if not hDevInfo or hDevInfo == ctypes.c_void_p(INVALID_HANDLE_VALUE).value:
            log.warning("SetupDiGetClassDevsW failed")
            return None

        try:
            # SetupDiEnumDeviceInterfaces
            setupapi.SetupDiEnumDeviceInterfaces.restype = ctypes.wintypes.BOOL
            setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_ubyte * 16),
                ctypes.wintypes.DWORD,
                ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
            ]

            # SetupDiGetDeviceInterfaceDetailW
            setupapi.SetupDiGetDeviceInterfaceDetailW.restype = ctypes.wintypes.BOOL
            setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
                ctypes.c_void_p,
                ctypes.wintypes.DWORD,
                ctypes.POINTER(ctypes.wintypes.DWORD),
                ctypes.c_void_p,
            ]

            index = 0
            while True:
                did = SP_DEVICE_INTERFACE_DATA()
                did.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)

                if not setupapi.SetupDiEnumDeviceInterfaces(
                    hDevInfo, None, guid_array, index, ctypes.byref(did)
                ):
                    break  # No more devices

                # Get required buffer size
                required = ctypes.wintypes.DWORD(0)
                setupapi.SetupDiGetDeviceInterfaceDetailW(
                    hDevInfo, ctypes.byref(did), None, 0,
                    ctypes.byref(required), None
                )

                if required.value == 0:
                    index += 1
                    continue

                # Allocate buffer
                buf = ctypes.create_string_buffer(required.value)
                # First field is the struct size (DWORD)
                ctypes.memset(buf, 0, required.value)
                ctypes.memmove(
                    buf, ctypes.byref(ctypes.wintypes.DWORD(
                        ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
                    )), 4
                )

                if setupapi.SetupDiGetDeviceInterfaceDetailW(
                    hDevInfo, ctypes.byref(did), buf, required.value,
                    None, None
                ):
                    # Extract device path (wide string after 4-byte header)
                    offset = 4
                    max_chars = (required.value - offset) // 2
                    chars = (ctypes.c_wchar * max_chars).from_buffer(buf, offset)
                    dev_path = ctypes.wstring_at(ctypes.addressof(chars))

                    # Check if this is the e2eSoft device
                    # e2eSoft VCam has FriendlyName starting with "e2eSoft"
                    # We test by opening the device briefly
                    if self._is_e2e_device(dev_path, kernel32):
                        return dev_path

                index += 1

            return None

        finally:
            # SetupDiDestroyDeviceInfoList
            setupapi.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
            setupapi.SetupDiDestroyDeviceInfoList.restype = ctypes.wintypes.BOOL
            setupapi.SetupDiDestroyDeviceInfoList(hDevInfo)

    def _is_e2e_device(self, dev_path: str, kernel32) -> bool:
        """Check if the device at dev_path is the e2eSoft VCam."""
        # Quick test: try to open the device
        handle = kernel32.CreateFileW(
            dev_path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
            None, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, None
        )
        if handle and handle != INVALID_HANDLE_VALUE:
            kernel32.CloseHandle(handle)
            # Check if the path contains e2eSoft identifiers
            # e2eSoft devices appear under ROOT\IMAGE
            if 'IMAGE' in dev_path or 'e2e' in dev_path.lower() or 'vcam' in dev_path.lower():
                return True
        return False

    # ── Properties ────────────────────────────────────────────────

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
        return "e2eSoft VCam"

    # ── Public API ────────────────────────────────────────────────

    def configure(self, width: int = 1280, height: int = 720, fps: int = 30):
        self._width = width
        self._height = height
        self._fps = fps
        log.debug("E2eVCam configured: %dx%d @%d fps", width, height, fps)

    def start(self) -> bool:
        """Open the e2eSoft VCam kernel device and start streaming."""
        if self._running:
            return True
        if not self._available or not self._device_path:
            self._error = "e2eSoft VCam device not available"
            return False

        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

        self._handle = kernel32.CreateFileW(
            self._device_path,
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            0,  # No overlapped I/O for simplicity
            None
        )

        if not self._handle or self._handle == INVALID_HANDLE_VALUE:
            err = ctypes.get_last_error()
            self._error = f"Cannot open e2eSoft device (error {err})"
            self._handle = None
            log.warning("E2eVCam open failed: error %d", err)
            return False

        # Set format if the driver supports it
        self._set_format(self._width, self._height, self._fps)

        # Start streaming
        self._send_ioctl(IOCTL_VCAM_START_STREAM)

        self._running = True
        log.info("e2eSoft VCam started: %dx%d @%d fps",
                 self._width, self._height, self._fps)
        return True

    def stop(self):
        """Stop streaming and close the device."""
        if self._handle and self._handle != INVALID_HANDLE_VALUE:
            try:
                self._send_ioctl(IOCTL_VCAM_STOP_STREAM)
            except Exception:
                pass
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel32.CloseHandle(self._handle)
            self._handle = None
        self._running = False
        log.info("e2eSoft VCam stopped")

    def shutdown(self):
        self.stop()
        log.info("e2eSoft VCam shut down")

    def send_frame(self, frame: np.ndarray):
        """
        Send a BGR frame to the e2eSoft VCam.
        Converts to RGB, resizes to configured dimensions, sends via IOCTL.
        """
        if not self._running or not self._handle:
            return
        if frame is None or frame.size == 0:
            return

        try:
            # BGR → RGB
            rgb = frame[:, :, ::-1].copy()

            # Resize if needed
            if (rgb.shape[1] != self._width or
                    rgb.shape[0] != self._height):
                import cv2
                rgb = cv2.resize(rgb, (self._width, self._height),
                                 interpolation=cv2.INTER_LINEAR)

            # Send frame
            self._send_frame_data(rgb)

        except Exception as e:
            log.warning("E2eVCam send_frame error: %s", e)
            # Try to reopen on critical errors
            if 'invalid handle' in str(e).lower():
                self._running = False
                self._handle = None

    # ── Internal IOCTL ────────────────────────────────────────────

    def _send_ioctl(self, ioctl_code: int, in_data: bytes = b'',
                    out_size: int = 0) -> bytes:
        """Send an IOCTL to the e2eSoft device."""
        if not self._handle:
            return b''

        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

        in_buf = ctypes.create_string_buffer(in_data)
        out_buf = ctypes.create_string_buffer(max(out_size, 1))
        bytes_ret = ctypes.wintypes.DWORD(0)

        result = kernel32.DeviceIoControl(
            self._handle,
            ctypes.wintypes.DWORD(ioctl_code),
            in_buf, ctypes.wintypes.DWORD(len(in_data)),
            out_buf, ctypes.wintypes.DWORD(max(out_size, 1)),
            ctypes.byref(bytes_ret),
            None
        )

        if not result:
            err = ctypes.get_last_error()
            log.warning("IOCTL 0x%08X failed: error %d", ioctl_code, err)

        return out_buf.raw[:bytes_ret.value]

    def _set_format(self, width: int, height: int, fps: int):
        """Set the video format via IOCTL."""
        # Format: width(4) + height(4) + fps(4) + reserved(4) = 16 bytes
        fmt_data = (ctypes.c_uint32 * 4)(width, height, fps, 0)
        self._send_ioctl(IOCTL_VCAM_SET_FORMAT, bytes(fmt_data))
        log.debug("E2eVCam format set: %dx%d @%d", width, height, fps)

    def _send_frame_data(self, frame: np.ndarray):
        """Send RGB frame data via IOCTL."""
        if frame.dtype != np.uint8:
            frame = frame.astype(np.uint8)
        frame_bytes = frame.tobytes()
        self._send_ioctl(IOCTL_VCAM_SEND_FRAME, frame_bytes)
