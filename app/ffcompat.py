"""
PixelMorph FF-compat layer.

Standalone implementations of the face math the swap pipeline needs
(anchor decoding for SCRFD, ArcFace warp templates, affine paste-back,
box masks, pixel-boost tiling, NMS). Originally adapted from the
FaceFusion helper routines; rewritten here so PixelMorph has no
large-external-dependency requirement.

All functions are pure numpy + OpenCV; numerics match the upstream
versions the engine was tuned against.
"""

from functools import lru_cache
from typing import List, Sequence, Tuple

import cv2
import numpy as np

from app.logger import get_logger

log = get_logger(__name__)

# ── Warp templates ────────────────────────────────────────────────────────
# Normalized (x, y) landmark anchor positions for face-crop alignment.

WARP_TEMPLATE_SET = {
    "arcface_112_v1": np.array([
        [0.35473214, 0.45658929],
        [0.64526786, 0.45658929],
        [0.50000000, 0.61154464],
        [0.37913393, 0.77687500],
        [0.62086607, 0.77687500],
    ]),
    "arcface_112_v2": np.array([
        [0.34191607, 0.46157411],
        [0.65653393, 0.45983393],
        [0.50022500, 0.64050536],
        [0.37097589, 0.82469196],
        [0.63151696, 0.82325089],
    ]),
    "arcface_128": np.array([
        [0.36167656, 0.40387734],
        [0.63696719, 0.40235469],
        [0.50019687, 0.56044219],
        [0.38710391, 0.72160547],
        [0.61507734, 0.72034453],
    ]),
}


def estimate_matrix_by_face_landmark_5(face_landmark_5: np.ndarray,
                                       warp_template: str,
                                       crop_size: Tuple[int, int]) -> np.ndarray:
    """Estimate a partial-affine matrix aligning 5 landmarks to a template."""
    warp_template_norm = WARP_TEMPLATE_SET[warp_template] * crop_size
    affine_matrix = cv2.estimateAffinePartial2D(
        face_landmark_5, warp_template_norm,
        method=cv2.RANSAC, ransacReprojThreshold=100)[0]
    return affine_matrix


def warp_face_by_face_landmark_5(vision_frame: np.ndarray,
                                 face_landmark_5: np.ndarray,
                                 warp_template: str,
                                 crop_size: Tuple[int, int]
                                 ) -> Tuple[np.ndarray, np.ndarray]:
    """Warp a frame so the face sits in `crop_size` per the template."""
    affine_matrix = estimate_matrix_by_face_landmark_5(
        face_landmark_5, warp_template, crop_size)
    crop_vision_frame = cv2.warpAffine(
        vision_frame, affine_matrix, crop_size,
        borderMode=cv2.BORDER_REPLICATE, flags=cv2.INTER_AREA)
    return crop_vision_frame, affine_matrix


def transform_points(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Apply an affine matrix to an (N, 2) point array."""
    points = points.reshape(-1, 1, 2)
    points = cv2.transform(points, matrix)
    points = points.reshape(-1, 2)
    return points


def paste_back(vision_frame: np.ndarray,
               crop_vision_frame: np.ndarray,
               crop_vision_mask: np.ndarray,
               affine_matrix: np.ndarray) -> np.ndarray:
    """Paste a warped face crop back into the original frame via its mask."""
    paste_bounding_box, paste_matrix = _calculate_paste_area(
        vision_frame, crop_vision_frame, affine_matrix)
    x1, y1, x2, y2 = paste_bounding_box
    paste_width = x2 - x1
    paste_height = y2 - y1
    inverse_vision_mask = cv2.warpAffine(
        crop_vision_mask, paste_matrix, (paste_width, paste_height)).clip(0, 1)
    inverse_vision_mask = np.expand_dims(inverse_vision_mask, axis=-1)
    inverse_vision_frame = cv2.warpAffine(
        crop_vision_frame, paste_matrix, (paste_width, paste_height),
        borderMode=cv2.BORDER_REPLICATE)
    temp_vision_frame = vision_frame.copy()
    paste_vision_frame = temp_vision_frame[y1:y2, x1:x2]
    paste_vision_frame = (paste_vision_frame * (1 - inverse_vision_mask)
                          + inverse_vision_frame * inverse_vision_mask)
    temp_vision_frame[y1:y2, x1:x2] = paste_vision_frame.astype(
        temp_vision_frame.dtype)
    return temp_vision_frame


def _calculate_paste_area(vision_frame: np.ndarray,
                          crop_vision_frame: np.ndarray,
                          affine_matrix: np.ndarray
                          ) -> Tuple[np.ndarray, np.ndarray]:
    """Compute the region of the frame where the crop will be pasted."""
    temp_height, temp_width = vision_frame.shape[:2]
    crop_height, crop_width = crop_vision_frame.shape[:2]
    inverse_matrix = cv2.invertAffineTransform(affine_matrix)
    crop_points = np.array([
        [0, 0], [crop_width, 0], [crop_width, crop_height], [0, crop_height]
    ])
    paste_region_points = transform_points(crop_points, inverse_matrix)
    paste_region_point_min = np.floor(
        paste_region_points.min(axis=0)).astype(int)
    paste_region_point_max = np.ceil(
        paste_region_points.max(axis=0)).astype(int)
    x1, y1 = np.clip(paste_region_point_min, 0, [temp_width, temp_height])
    x2, y2 = np.clip(paste_region_point_max, 0, [temp_width, temp_height])
    paste_bounding_box = np.array([x1, y1, x2, y2])
    paste_matrix = inverse_matrix.copy()
    paste_matrix[0, 2] -= x1
    paste_matrix[1, 2] -= y1
    return paste_bounding_box, paste_matrix


def create_static_anchors(feature_stride: int, anchor_total: int,
                          stride_height: int, stride_width: int) -> np.ndarray:
    """Generate SCRFD (y, x) anchor centers for a feature-map stride."""
    x, y = np.mgrid[:stride_width, :stride_height]
    anchors = np.stack((y, x), axis=-1)
    anchors = (anchors * feature_stride).reshape((-1, 2))
    anchors = np.stack([anchors] * anchor_total, axis=1).reshape((-1, 2))
    return anchors


def distance_to_bounding_box(points: np.ndarray,
                             distance: np.ndarray) -> np.ndarray:
    """Decode SCRFD bbox distances into (x1, y1, x2, y2)."""
    x1 = points[:, 0] - distance[:, 0]
    y1 = points[:, 1] - distance[:, 1]
    x2 = points[:, 0] + distance[:, 2]
    y2 = points[:, 1] + distance[:, 3]
    bounding_box = np.column_stack([x1, y1, x2, y2])
    return bounding_box


def distance_to_face_landmark_5(points: np.ndarray,
                                distance: np.ndarray) -> np.ndarray:
    """Decode SCRFD landmark distances into (N, 5, 2)."""
    x = points[:, 0::2] + distance[:, 0::2]
    y = points[:, 1::2] + distance[:, 1::2]
    face_landmark_5 = np.stack((x, y), axis=-1)
    return face_landmark_5


def apply_nms(bounding_boxes: List[np.ndarray], scores: List[float],
              score_threshold: float, nms_threshold: float) -> List[int]:
    """cv2.dnn.NMSBoxes wrapped for (x1, y1, x2, y2) boxes."""
    bounding_boxes_norm = [
        (x1, y1, x2 - x1, y2 - y1)
        for (x1, y1, x2, y2) in bounding_boxes
    ]
    keep_indices = cv2.dnn.NMSBoxes(
        bounding_boxes_norm, scores,
        score_threshold=score_threshold, nms_threshold=nms_threshold)
    return keep_indices


def create_box_mask(crop_vision_frame: np.ndarray, face_mask_blur: float,
                    face_mask_padding: Tuple[int, int, int, int]
                    ) -> np.ndarray:
    """Feathered rect mask over the crop (top/right/bottom/left % padding)."""
    crop_size = crop_vision_frame.shape[:2][::-1]
    blur_amount = int(crop_size[0] * 0.5 * face_mask_blur)
    blur_area = max(blur_amount // 2, 1)
    box_mask = np.ones(crop_size).astype(np.float32)
    box_mask[:max(blur_area, int(crop_size[1] * face_mask_padding[0] / 100)), :] = 0
    box_mask[-max(blur_area, int(crop_size[1] * face_mask_padding[2] / 100)):, :] = 0
    box_mask[:, :max(blur_area, int(crop_size[0] * face_mask_padding[3] / 100))] = 0
    box_mask[:, -max(blur_area, int(crop_size[0] * face_mask_padding[1] / 100)):] = 0

    if blur_amount > 0:
        box_mask = cv2.GaussianBlur(box_mask, (0, 0), blur_amount * 0.25)
    return box_mask


def implode_pixel_boost(crop_vision_frame: np.ndarray,
                        pixel_boost_total: int,
                        model_size: Tuple[int, int]) -> np.ndarray:
    """Tile a square crop into (total**2, model_h, model_w, 3) sub-tiles."""
    pixel_boost_vision_frame = crop_vision_frame.reshape(
        model_size[0], pixel_boost_total, model_size[1], pixel_boost_total, 3)
    pixel_boost_vision_frame = pixel_boost_vision_frame.transpose(
        1, 3, 0, 2, 4).reshape(
        pixel_boost_total ** 2, model_size[0], model_size[1], 3)
    return pixel_boost_vision_frame


def explode_pixel_boost(temp_vision_frames: List[np.ndarray],
                        pixel_boost_total: int,
                        model_size: Tuple[int, int],
                        pixel_boost_size: Tuple[int, int]) -> np.ndarray:
    """Reassemble swapped sub-tiles back into the full-size crop."""
    crop_vision_frame = np.stack(temp_vision_frames).reshape(
        pixel_boost_total, pixel_boost_total,
        model_size[0], model_size[1], 3)
    crop_vision_frame = crop_vision_frame.transpose(
        2, 0, 3, 1, 4).reshape(pixel_boost_size[0], pixel_boost_size[1], 3)
    return crop_vision_frame


def restrict_frame(vision_frame: np.ndarray,
                   resolution: Tuple[int, int]) -> np.ndarray:
    """Downscale a frame proportionally to fit inside `resolution`."""
    height, width = vision_frame.shape[:2]
    restrict_width, restrict_height = resolution
    if height > restrict_height or width > restrict_width:
        scale = min(restrict_height / height, restrict_width / width)
        new_width = int(width * scale)
        new_height = int(height * scale)
        return cv2.resize(vision_frame, (new_width, new_height))
    return vision_frame


def unpack_resolution(resolution: str) -> Tuple[int, int]:
    """Turn '640x640' into (640, 640)."""
    width, height = map(int, resolution.split("x"))
    return width, height
