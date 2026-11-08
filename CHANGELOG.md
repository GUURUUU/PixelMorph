# Changelog

## v1.0.0 — 2026-11-08

First public release.

### Highlights
- Real-time webcam face swap (SCRFD + ArcFace + inswapper/hyperswap ONNX)
- Virtual camera output that appears in every app with a camera picker
  (OBS Virtual Camera, UnityCapture "PixelMorph" filter, e2eSoft, DShow)
- Automatic real-camera detection: physical webcams win over virtual ones
  every launch; manual choice is remembered by device name
- Holographic PyQt6 control deck: threshold / weight / resize sliders,
  pixel-boost 128–1024, frame skip, CLAHE / sharpen / white balance filters
- Snapshot + recording of the swap output (H.264 mp4 or mjpeg avi)
- BestCam Media Foundation virtual camera (C++, + Android MJPEG app)
- Standalone face-math module `app/ffcompat.py`, golden-tested against
  upstream FaceFusion implementations
- Headless self-tests: `scripts/e2e_selftest.py`, `scripts/vcam_feed_test.py`
- Model resolution: `PIXELMORPH_MODELS` env → `models_path.txt` → `models/`
  → upstream `.assets`, with a friendly pointer to the downloader script
