"""
Face Engine — face detection, recognition, and swapping core.

Self-contained; copied from live_swap.py and adapted for PixelMorph GUI.
"""

import logging
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from app.logger import get_logger

log = get_logger(__name__)

import cv2
import numpy as np
import onnxruntime

# ── Model resolution ──────────────────────────────────────────────────────
# Order: PIXELMORPH_MODELS env → /models_path.txt pointer → repo /models →
# sibling facefusion clone (.assets/models). Models are never in git;
# run scripts/download_models.py to fetch them.
_model_candidates = []
_env_dir = os.environ.get("PIXELMORPH_MODELS")
if _env_dir:
    _model_candidates.append(Path(_env_dir))
_ptr = Path(__file__).resolve().parent.parent / "models_path.txt"
if _ptr.exists():
    try:
        with open(_ptr) as f:
            _alt = f.read().strip()
        if _alt:
            _model_candidates.append(Path(_alt))
    except Exception:
        pass
_model_candidates += [
    Path(__file__).resolve().parent.parent / "models",
    Path(__file__).resolve().parent.parent / "facefusion" / ".assets" / "models",
]

MODELS_DIR: Optional[Path] = next(
    (c for c in _model_candidates
     if c.is_file() and c.suffix == ".onnx" and c.exists()
     ) if _env_dir and _env_dir.lower().endswith(".onnx")
    else (c for c in _model_candidates
          if c.exists() and any(c.glob("*.onnx"))),
    None)

if MODELS_DIR is None:
    raise FileNotFoundError(
        "No ONNX models found. Either:\n"
        "  1. run:  python scripts/download_models.py\n"
        "  2. set PIXELMORPH_MODELS to a folder holding .onnx files\n"
        "  3. write an absolute folder path into models_path.txt\n"
        f"Searched: {[_c.as_posix() if isinstance(_c, Path) else _c for _c in _model_candidates]}")

log.info("Models directory: %s", MODELS_DIR)

# Models that may exist; loaded only if present on disk.
MODEL_FILES = {
    "inswapper_128":    MODELS_DIR / "inswapper_128.onnx",
    "hyperswap_1a_256": MODELS_DIR / "hyperswap_1a_256.onnx",
}
MODEL_FILES = {k: str(v) for k, v in MODEL_FILES.items() if Path(str(v)).exists()}
SCRFD_PATH = str(MODELS_DIR / "scrfd_2.5g.onnx")
ARCFACE_PATH = str(MODELS_DIR / "arcface_w600k_r50.onnx")

_missing_required = [p for p in (SCRFD_PATH, ARCFACE_PATH)
                     if not os.path.exists(p)]
if _missing_required:
    raise FileNotFoundError(
        f"Required detection/recognition models missing: {_missing_required}\n"
        "Run: python scripts/download_models.py")
if not MODEL_FILES:
    raise FileNotFoundError(
        "No swapper model found (inswapper_128.onnx / hyperswap_1a_256.onnx).\n"
        "Run: python scripts/download_models.py")

# PixelMorph standalone face math (no external dependency)
log.debug("Importing standalone ff-compat helpers...")
from app.ffcompat import (
    apply_nms,
    create_box_mask,
    create_static_anchors,
    distance_to_bounding_box,
    distance_to_face_landmark_5,
    explode_pixel_boost,
    implode_pixel_boost,
    paste_back,
    restrict_frame,
    unpack_resolution,
    warp_face_by_face_landmark_5,
)

# ── Model configurations ──────────────────────────────────────────────────
MODEL_CONFIGS: Dict[str, dict] = {
    "inswapper_128": {
        "session":     None,
        "template":    "arcface_128",
        "size":        (128, 128),
        "mean":        [0.0, 0.0, 0.0],
        "std":         [1.0, 1.0, 1.0],
        "use_initializer": True,
    },
    "hyperswap_1a_256": {
        "session":     None,
        "template":    "arcface_128",
        "size":        (256, 256),
        "mean":        [0.5, 0.5, 0.5],
        "std":         [0.5, 0.5, 0.5],
        "use_initializer": False,
    },
}

# ── ONNX provider preference ──────────────────────────────────────────────
_PROVIDER_PREF = ["CUDAExecutionProvider", "CPUExecutionProvider"]


def _create_session(path: str) -> onnxruntime.InferenceSession:
    log.debug("Creating ONNX session for %s", os.path.basename(path))
    for i in range(len(_PROVIDER_PREF)):
        providers = _PROVIDER_PREF[:len(_PROVIDER_PREF) - i]
        try:
            session = onnxruntime.InferenceSession(path, providers=providers)
            log.info("Session created: %s with providers=%s",
                     os.path.basename(path), providers)
            return session
        except Exception as e:
            log.warning("Session failed with %s: %s", providers, e)
            continue
    log.warning("Falling back to CPU only for %s", os.path.basename(path))
    return onnxruntime.InferenceSession(path, providers=["CPUExecutionProvider"])


# ── Face Engine Class ─────────────────────────────────────────────────────
class FaceEngine:
    """
    Central face detection + recognition + swapping engine.

    Manages all ONNX sessions and provides a clean API for the GUI.
    """

    def __init__(self):
        log.info("Initializing FaceEngine...")
        self.scrfd_session   = _create_session(SCRFD_PATH)
        self.arcface_session = _create_session(ARCFACE_PATH)
        self._scrfd_input = self.scrfd_session.get_inputs()[0].name
        self._arcface_input = self.arcface_session.get_inputs()[0].name
        log.debug("SCRFD input=%s, ArcFace input=%s", self._scrfd_input, self._arcface_input)

        # Load swapper sessions (only models present on disk)
        for name in list(MODEL_CONFIGS):
            if name not in MODEL_FILES:
                log.info("Swapper model not found on disk, skipping: %s", name)
                del MODEL_CONFIGS[name]
                continue
            log.info("Loading swapper model: %s", name)
            MODEL_CONFIGS[name]["session"] = _create_session(MODEL_FILES[name])
            # Log model input names
            try:
                inp_names = [i.name for i in MODEL_CONFIGS[name]["session"].get_inputs()]
                log.debug("Model %s inputs: %s", name, inp_names)
            except Exception as e:
                log.warning("Could not inspect model %s inputs: %s", name, e)

        # InSwapper initializer
        log.debug("Loading InSwapper initializer...")
        import onnx
        import onnx.numpy_helper
        _model_onnx = onnx.load(MODEL_FILES["inswapper_128"])
        self.model_initializer = onnx.numpy_helper.to_array(
            _model_onnx.graph.initializer[-1])
        log.debug("InSwapper initializer loaded, shape=%s", self.model_initializer.shape)

        self.available_models = list(MODEL_CONFIGS.keys())
        self._source_cache: dict = {}
        log.info("FaceEngine initialized. Models: %s", self.available_models)

    # ── Face Detection ────────────────────────────────────────────────────

    def detect_faces(self, vision_frame: np.ndarray,
                     threshold: float = 0.5) -> List[dict]:
        """Detect faces in frame. Returns list of face dicts sorted by size."""
        t0 = time.perf_counter()
        bboxes, scores, landmarks = self._detect_scrfd(
            vision_frame, face_detector_score=threshold)
        if not bboxes:
            log.debug("detect_faces: no faces detected (threshold=%.2f)", threshold)
            return []
        keep = apply_nms(bboxes, scores, threshold, 0.4)
        faces = [self._make_face(vision_frame, bboxes[i], scores[i], landmarks[i])
                 for i in keep]
        faces.sort(key=lambda f:
            (f["bbox"][2] - f["bbox"][0]) * (f["bbox"][3] - f["bbox"][1]),
            reverse=True)
        elapsed = (time.perf_counter() - t0) * 1000
        log.debug("detect_faces: %d faces in %.1fms (threshold=%.2f)",
                  len(faces), elapsed, threshold)
        for i, f in enumerate(faces):
            log.log(logging.DEBUG - 1 if hasattr(logging, 'DEBUG') else 5,
                    "  Face[%d] score=%.3f bbox=%s", i, f["score"], f["bbox"])
        return faces

    def detect_faces_with_boxes(self, vision_frame: np.ndarray,
                                threshold: float = 0.5
                                ) -> Tuple[List[dict], List[np.ndarray]]:
        """Like detect_faces but also returns pixel-coordinate bboxes for overlay."""
        faces = self.detect_faces(vision_frame, threshold)
        return faces

    # ── Source Face Loading ───────────────────────────────────────────────

    def load_source(self, image: np.ndarray, threshold: float = 0.5
                    ) -> List[dict]:
        """Detect faces in a source image. Returns sorted list."""
        return self.detect_faces(image, threshold)

    def prepare_embedding(self, face: dict, model_name: str) -> np.ndarray:
        """Prepare source embedding for the given model."""
        cfg = MODEL_CONFIGS[model_name]
        log.debug("prepare_embedding for model=%s use_initializer=%s",
                  model_name, cfg["use_initializer"])
        if cfg["use_initializer"]:
            emb = face["embedding"].reshape((1, -1))
            result = emb @ self.model_initializer / np.linalg.norm(emb)
            log.debug("Embedding projected via initializer, shape=%s, norm=%.4f",
                      result.shape, np.linalg.norm(result))
            return result
        else:
            result = face["embedding_norm"].reshape((1, -1)).copy()
            log.debug("Embedding copied directly, shape=%s, norm=%.4f",
                      result.shape, np.linalg.norm(result))
            return result

    # ── Face Swap ─────────────────────────────────────────────────────────

    def swap_face(self,
                  source_embedding: np.ndarray,
                  target_face: dict,
                  target_frame: np.ndarray,
                  model_name: str = "hyperswap_1a_256",
                  pixel_boost: int = 512,
                  weight: float = 0.5,
                  ) -> np.ndarray:
        """Swap the target face using the source embedding. Returns modified frame."""
        t0 = time.perf_counter()
        cfg = MODEL_CONFIGS[model_name]
        session = cfg["session"]
        native_size = cfg["size"]
        boost_size = (pixel_boost, pixel_boost) if pixel_boost > native_size[0] else native_size
        log.debug("swap_face: model=%s pb=%d weight=%.2f target_score=%.3f",
                  model_name, pixel_boost, weight, target_face.get("score", 0))

        crop_frame, affine = warp_face_by_face_landmark_5(
            target_frame, target_face["landmark_5_68"],
            cfg["template"], boost_size)
        log.log(logging.DEBUG - 1 if hasattr(logging, 'DEBUG') else 5,
                "  warp done, crop shape=%s", crop_frame.shape)

        # Blend source → target embedding
        t_emb = target_face["embedding_norm"].reshape(1, -1)
        interp_w = float(np.interp(weight, [0, 1], [0.35, -0.35]))
        t_emb = t_emb / np.linalg.norm(t_emb)
        final_emb = source_embedding * (1 - interp_w) + t_emb * interp_w
        log.debug("  embedding blended, interp_w=%.3f", interp_w)

        # Pixel boost tiling
        if pixel_boost > native_size[0]:
            total_tiles = pixel_boost // native_size[0]
            tiles = implode_pixel_boost(crop_frame, total_tiles, native_size)
            log.debug("  pixel boost: %d×%dpx in %d tiles", pixel_boost, pixel_boost, total_tiles)
            out_tiles = []
            for ti, tile in enumerate(tiles):
                inp = self._prepare_crop(tile, cfg)
                outs = session.run(None, {
                    "source": final_emb.astype(np.float32),
                    "target": inp,
                })
                out_tiles.append(self._normalize_crop(outs[0][0], cfg))
                log.log(logging.DEBUG - 1 if hasattr(logging, 'DEBUG') else 5,
                        "  tile %d/%d done", ti + 1, total_tiles)
            crop_frame_out = explode_pixel_boost(
                out_tiles, total_tiles, native_size, boost_size)
        else:
            inp = self._prepare_crop(crop_frame, cfg)
            outs = session.run(None, {
                "source": final_emb.astype(np.float32),
                "target": inp,
            })
            crop_frame_out = self._normalize_crop(outs[0][0], cfg)

        mask = create_box_mask(crop_frame_out, face_mask_blur=0.3,
                               face_mask_padding=(0, 0, 0, 0))
        result = paste_back(target_frame, crop_frame_out, mask, affine)
        elapsed = (time.perf_counter() - t0) * 1000
        log.debug("swap_face done in %.1fms", elapsed)
        return result

    # ── Batch helpers ─────────────────────────────────────────────────────

    def swap_image_file(self,
                        source_embedding: np.ndarray,
                        target_image: np.ndarray,
                        source_faces: List[dict],
                        model_name: str = "hyperswap_1a_256",
                        pixel_boost: int = 512,
                        weight: float = 0.5,
                        threshold: float = 0.35,
                        ) -> np.ndarray:
        """Swap all detected faces in a target image. Returns modified image."""
        log.info("swap_image_file: image=%s, model=%s, pb=%d",
                 target_image.shape, model_name, pixel_boost)
        t0 = time.perf_counter()
        result = target_image.copy()
        target_faces = self.detect_faces(result, threshold)
        if not target_faces:
            log.warning("swap_image_file: no target faces detected")
            return result
        log.info("swap_image_file: swapping %d target faces", len(target_faces))
        for i, tface in enumerate(target_faces):
            log.debug("  swapping target face %d/%d (score=%.3f)",
                      i + 1, len(target_faces), tface["score"])
            result = self.swap_face(
                source_embedding, tface, result,
                model_name=model_name, pixel_boost=pixel_boost, weight=weight)
        elapsed = time.perf_counter() - t0
        log.info("swap_image_file completed in %.2fs", elapsed)
        return result

    # ── Internal methods ──────────────────────────────────────────────────

    def _detect_scrfd(self, vision_frame: np.ndarray,
                      face_detector_size: str = "640x640",
                      face_detector_score: float = 0.5
                      ) -> Tuple[List[np.ndarray], List[float], List[np.ndarray]]:
        t0 = time.perf_counter()
        h, w = vision_frame.shape[:2]
        fw, fh = unpack_resolution(face_detector_size)
        temp = restrict_frame(vision_frame, (fw, fh))
        rh, rw = h / temp.shape[0], w / temp.shape[1]

        detect = np.zeros((fh, fw, 3), dtype=np.float32)
        detect[:temp.shape[0], :temp.shape[1]] = temp
        detect = np.expand_dims(detect.transpose(2, 0, 1), axis=0)
        detect = (detect - 127.5) / 128.0

        try:
            outs = self.scrfd_session.run(None, {self._scrfd_input: detect})
        except Exception as e:
            log.error("SCRFD inference failed: %s", traceback.format_exc())
            return [], [], []

        bboxes, scores, landmarks = [], [], []
        for idx, stride in enumerate([8, 16, 32]):
            s_h, s_w = fh // stride, fw // stride
            anchors = create_static_anchors(stride, 2, s_h, s_w)
            score_raw = outs[idx]
            keep = np.where(score_raw >= face_detector_score)[0]
            if not np.any(keep):
                continue
            bbox_raw = outs[idx + 3] * stride
            lm_raw   = outs[idx + 6] * stride
            bbox_dist = distance_to_bounding_box(anchors, bbox_raw)[keep]
            lm_dist   = distance_to_face_landmark_5(anchors, lm_raw)[keep]
            for bb in bbox_dist:
                bboxes.append(np.array([bb[0]*rw, bb[1]*rh, bb[2]*rw, bb[3]*rh]))
            for sc in score_raw[keep]:
                scores.append(float(sc[0]))
            for lm in lm_dist:
                landmarks.append(lm * [rw, rh])
        elapsed = (time.perf_counter() - t0) * 1000
        log.debug("_detect_scrfd: %d candidates in %.1fms", len(scores), elapsed)
        return bboxes, scores, landmarks

    def _calc_embedding(self, vision_frame: np.ndarray,
                        landmark_5: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        t0 = time.perf_counter()
        crop, _ = warp_face_by_face_landmark_5(
            vision_frame, landmark_5, "arcface_112_v2", (112, 112))
        crop = crop / 127.5 - 1.0
        crop = crop[:, :, ::-1].transpose(2, 0, 1).astype(np.float32)
        crop = np.expand_dims(crop, axis=0)
        try:
            (emb,) = self.arcface_session.run(None, {self._arcface_input: crop})
        except Exception as e:
            log.error("ArcFace inference failed: %s", traceback.format_exc())
            raise
        emb = emb.ravel()
        emb_norm = emb / np.linalg.norm(emb)
        elapsed = (time.perf_counter() - t0) * 1000
        log.log(logging.DEBUG - 1 if hasattr(logging, 'DEBUG') else 5,
                "  embedding calc in %.1fms, norm=%.4f", elapsed, np.linalg.norm(emb))
        return emb, emb_norm

    def _make_face(self, vision_frame: np.ndarray, bbox: np.ndarray,
                   score: float, landmark_5: np.ndarray) -> dict:
        embedding, embedding_norm = self._calc_embedding(vision_frame, landmark_5)
        dx = landmark_5[1, 0] - landmark_5[0, 0]
        dy = landmark_5[1, 1] - landmark_5[0, 1]
        angle = float(np.degrees(np.arctan2(dy, dx)))
        face = {
            "bbox": bbox,
            "score": score,
            "landmark_5": landmark_5,
            "landmark_5_68": landmark_5.copy(),
            "embedding": embedding,
            "embedding_norm": embedding_norm,
            "angle": angle,
        }
        log.debug("_make_face: score=%.3f angle=%.1f bbox=%s", score, angle, bbox)
        return face

    @staticmethod
    def _prepare_crop(crop_frame: np.ndarray, cfg: dict) -> np.ndarray:
        out = crop_frame[:, :, ::-1].astype(np.float32) / 255.0
        out = (out - np.array(cfg["mean"], dtype=np.float32)) / np.array(cfg["std"], dtype=np.float32)
        out = out.transpose(2, 0, 1)
        out = np.expand_dims(out, axis=0).astype(np.float32)
        return out

    @staticmethod
    def _normalize_crop(raw_out: np.ndarray, cfg: dict) -> np.ndarray:
        out = raw_out.transpose(1, 2, 0)
        out = out * np.array(cfg["std"], dtype=np.float32) + np.array(cfg["mean"], dtype=np.float32)
        out = out.clip(0, 1)
        out = out[:, :, ::-1] * 255
        return out.astype(np.uint8)

    @staticmethod
    def get_model_native_size(model_name: str) -> int:
        return MODEL_CONFIGS[model_name]["size"][0]

    @staticmethod
    def validate_pixel_boost(model_name: str, pixel_boost: int) -> int:
        native = MODEL_CONFIGS[model_name]["size"][0]
        if pixel_boost == 0:
            return native
        if pixel_boost % native != 0:
            pixel_boost = (pixel_boost // native) * native
            if pixel_boost == 0:
                pixel_boost = native
        return pixel_boost
