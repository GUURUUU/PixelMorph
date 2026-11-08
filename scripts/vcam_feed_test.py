"""
Live virtual-camera feed test — proves PixelMorph's output path works in
real apps (WhatsApp / Zoom / Chrome / Windows Camera), no GUI needed.

Streams an animated test card through VirtualCameraOutput (the same class
the app uses). Watch for the moving bars + growing frame counter.

Usage:
    python scripts/vcam_feed_test.py                 # auto backend (OBS)
    python scripts/vcam_feed_test.py --backend obs   # OBS Virtual Camera
    python scripts/vcam_feed_test.py --backend unitycapture  # "PixelMorph" DS filter
    python scripts/vcam_feed_test.py --duration 300  # seconds (default 180)
"""
import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import cv2
import numpy as np
from app.logger import setup_logging
from app.virtual_cam import VirtualCameraOutput


def build_card(idx: int, t: float, backend: str, device: str) -> np.ndarray:
    w, h = 1280, 720
    img = np.zeros((h, w, 3), np.uint8)

    # scrolling vertical color bars (motion test)
    shift = int(t * 120) % 320
    palette = [(203, 68, 222), (68, 203, 222), (222, 68, 68),
               (222, 200, 68), (68, 222, 68), (222, 68, 203)]
    for x in range(0, w, 80):
        c = palette[((x + shift) // 80) % len(palette)]
        img[:, x:x + 80] = c

    # moving checkerboard strip (sharpness/blur test)
    cb = np.zeros((80, w), np.uint8)
    step = 40 + (idx % 3) * 10
    for x in range(0, w, step * 2):
        cb[:, x + (idx % 2) * step:x + step + (idx % 2) * step] = 255
    img[560:640] = cv2.cvtColor(cv2.addWeighted(cb, 0.35, cb, 0.0, 0), cv2.COLOR_GRAY2BGR)

    # captions
    cv2.putText(img, "PixelMorph VCAM FEED TEST", (30, 70),
                cv2.FONT_HERSHEY_SIMPLEX, 1.6, (255, 255, 255), 4, cv2.LINE_AA)
    cv2.putText(img, f"frame {idx:06d}", (30, 140),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(img, f"frame {idx:06d}", (32, 142),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(img, datetime.now().strftime("%H:%M:%S.%f")[:-3], (30, 200),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(img, f"backend={backend}   device={device}", (30, 260),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (30, 30, 30), 2, cv2.LINE_AA)
    cv2.circle(img, (w - 60, 60), 30, (60, 60, 255), -1)  # pulsing dot
    r = 30 + int(14 * np.sin(t * 4))
    cv2.circle(img, (w - 60, 60), max(4, r), (90, 120, 255), 6)
    return img


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default=None,
                    help="auto | obs | unitycapture | dshow")
    ap.add_argument("--duration", type=float, default=180.0)
    ap.add_argument("--fps", type=float, default=30.0)
    args = ap.parse_args()

    setup_logging()
    backend = None if args.backend in (None, "auto") else args.backend
    vo = VirtualCameraOutput(backend=backend) if backend else VirtualCameraOutput()

    if not vo.available:
        print("FAIL: no virtual camera backend available:", vo.error)
        return 1

    print("=" * 60)
    print(f"  STREAMING -> backend={vo.backend}  device='{vo.device_name}'")
    print(f"  In your app pick the camera named above.")
    print(f"  Runs for {args.duration:.0f}s. Ctrl+C to stop early.")
    print("=" * 60)

    vo.configure(1280, 720, args.fps)
    if not vo.start():
        print("FAIL: could not open camera:", vo.error)
        return 1

    t0 = time.perf_counter()
    idx = 0
    try:
        while time.perf_counter() - t0 < args.duration:
            frame = build_card(idx, time.perf_counter() - t0,
                               str(vo.backend), vo.device_name)
            vo.send_frame(frame)
            idx += 1
            time.sleep(1.0 / args.fps)
    except KeyboardInterrupt:
        pass
    finally:
        vo.stop()
    print(f"DONE: sent {idx} frames in {time.perf_counter() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
