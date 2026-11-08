"""
BestCam Live Test — sends a continuous test pattern so Snap Camera can detect it.
Press Ctrl+C to stop.
"""
import sys
import time
import numpy as np
import cv2

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
from app.bestcam_bridge import BestCamBridge

bridge = BestCamBridge()
if not bridge.connect():
    print("FAILED to connect to BestCam. Is BestCamHost.exe running?")
    sys.exit(1)

print("BestCam connected. Sending test frames...")
print("Open Snap Camera -> Settings -> Camera -> BestCam Virtual Webcam")

try:
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    t0 = time.time()
    while True:
        t = time.time() - t0
        # Animate a bouncing rectangle
        x = int(200 + 1500 * (0.5 + 0.5 * np.sin(t * 0.5)))
        y = int(200 + 600 * (0.5 + 0.5 * np.sin(t * 0.7)))
        frame[:] = (200, 100, 50)
        cv2.putText(frame, "PixelMorph + BestCam", (50, 200),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3)
        cv2.putText(frame, "NO WATERMARK!", (50, 300),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 0), 3)
        cv2.rectangle(frame, (x, y), (x + 200, y + 200), (0, 255, 255), -1)
        bridge.send(frame)
        time.sleep(1 / 30)  # ~30 fps
except KeyboardInterrupt:
    print("\nStopped.")
finally:
    bridge.disconnect()
