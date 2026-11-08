"""
PixelMorph end-to-end self-test — no GUI required.

Pipeline proven: detect -> crop/warp -> embed source -> swap -> paste-back,
using the exact FaceEngine path the GUI uses. If models are missing the test
exits gracefully (so it can double as a CI smoke job that SKIPS cleanly).

Usage:
    python scripts/e2e_selftest.py [--source PATH] [--target PATH] [--out PATH]
"""
import argparse
import os
import sys
import logging
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import cv2
import numpy as np
from app.logger import setup_logging


def _model_files():
    try:
        from app.face_engine import MODEL_FILES
        return MODEL_FILES
    except FileNotFoundError:
        return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=None, help="face to clone")
    ap.add_argument("--target", default=None, help="scene to paste into")
    ap.add_argument("--out", default=str(REPO_ROOT / "e2e_output.png"))
    args = ap.parse_args()

    setup_logging()
    log = logging.getLogger("e2e")

    model_files = _model_files()
    if not model_files:
        log.info("SKIP: no swapper models found "
                 "(set PIXELMORPH_MODELS or run scripts/download_models.py)")
        return 0

    src_path = args.source or Path(os.environ.get("TEMP", ".")) / "opencode" / "face_source.jpg"
    tgt_path = args.target or Path(os.environ.get("TEMP", ".")) / "opencode" / "target_two.jpg"
    if not src_path.exists() or not tgt_path.exists():
        log.warning("SKIP: test faces not present (%s / %s)", src_path, tgt_path)
        return 0

    from app.face_engine import FaceEngine
    engine = FaceEngine()
    if not engine.available_models:
        log.error("FAIL: engine reports no usable swapper models")
        return 1

    source = cv2.imread(str(src_path))
    target = cv2.imread(str(tgt_path))
    if source is None or target is None:
        log.error("FAIL: could not read input images")
        return 1

    model = engine.available_models[0]
    log.info("=== e2e with model '%s' ===", model)

    src_faces = engine.detect_faces(source, 0.35)
    tgt_faces = engine.detect_faces(target, 0.35)
    log.info("source faces: %d | target faces: %d", len(src_faces), len(tgt_faces))
    if not src_faces or not tgt_faces:
        log.error("FAIL: detection found nothing")
        return 1

    embedding = engine.prepare_embedding(src_faces[0], model)
    if embedding is None:
        log.error("FAIL: prepare_embedding returned None")
        return 1

    result = engine.swap_image_file(embedding, target, tgt_faces, model)
    if result is None:
        log.error("FAIL: swap returned None")
        return 1

    # sanity: face region must actually change
    bbox = tgt_faces[0]["bbox"].astype(int)
    x0, y0, x1, y1 = [max(0, v) for v in (bbox[0], bbox[1], bbox[2], bbox[3])]
    region_t = target[y0:y1, x0:x1].astype(np.float32)
    region_r = result[y0:y1, x0:x1].astype(np.float32)
    diff = float(np.mean(np.abs(region_t - region_r)))
    log.info("face-region mean abs diff: %.1f", diff)
    if diff < 5.0:
        log.error("FAIL: face region barely changed (diff=%.1f)", diff)
        return 1

    if source.shape[0] != target.shape[0]:
        scale = target.shape[0] / source.shape[0]
        source = cv2.resize(source, (int(source.shape[1] * scale), target.shape[0]))
    combo = np.hstack([source, np.full((target.shape[0], 4, 3), 255, np.uint8),
                       target, np.full((target.shape[0], 4, 3), 255, np.uint8),
                       result])
    cv2.imwrite(args.out, combo)
    log.info("PASS: wrote %s", args.out)
    try:
        os.startfile(args.out)  # pop it open for human eyes
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
