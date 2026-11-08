"""
Standalone tests for app/ffcompat.py — no models, no GUI, no upstream clone.
Signatures mirror the real API exactly.
Run: pytest tests/ -q
"""
import sys
from pathlib import Path

import numpy as np
import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ffcompat import (
    WARP_TEMPLATE_SET,
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


def test_unpack_resolution():
    assert unpack_resolution("640x640") == (640, 640)
    assert unpack_resolution("1920x1080") == (1920, 1080)


def test_restrict_frame_shrinks_and_passthrough():
    frame = np.zeros((1000, 1600, 3), np.uint8)  # bigger than 640x640
    out = restrict_frame(frame, (640, 640))
    assert max(out.shape[:2]) <= 640
    same = np.zeros((100, 100, 3), np.uint8)
    assert restrict_frame(same, (640, 640)) is same or restrict_frame(
        same, (640, 640)).shape == same.shape


def test_create_static_anchors_stride8():
    anchors = create_static_anchors(8, 2, 64, 64)
    arr = np.asarray(anchors)
    assert arr.shape == (2 * 64 * 64, 2)
    # first anchor for stride 8 should be (0,0)
    assert arr[0, 0] == 0 and arr[0, 1] == 0
    ys, xs = arr[:, 0], arr[:, 1]
    assert ys.max() == (64 - 1) * 8
    assert xs.max() == (64 - 1) * 8


def test_distance_decode_roundtrip():
    anchors = create_static_anchors(8, 2, 64, 64).astype(np.float32)[:200]
    distance = np.abs(np.random.rand(200, 4).astype(np.float32) * 30)
    bboxes = distance_to_bounding_box(anchors, distance)
    assert bboxes.shape == (200, 4)
    # x1 < x2, y1 < y2
    assert np.all(bboxes[:, 0] < bboxes[:, 2])
    assert np.all(bboxes[:, 1] < bboxes[:, 3])
    # landmarks: 10 distance values -> 5 points, x from even-index, y odd
    lms = np.random.rand(200, 10).astype(np.float32)
    pts = distance_to_face_landmark_5(anchors, lms)
    assert pts.shape == (200, 5, 2)


def test_apply_nms_keeps_best():
    boxes = [[0, 0, 100, 100], [5, 5, 105, 105], [300, 300, 400, 400]]
    scores = [0.9, 0.8, 0.7]
    kept = apply_nms(boxes, scores, score_threshold=0.35, nms_threshold=0.4)
    kept = np.asarray(kept).flatten().astype(int)
    assert 0 in kept          # best scoring box kept
    assert 1 not in kept      # heavily overlapping box suppressed
    assert 2 in kept          # far-away box kept


def test_warp_face_by_face_landmark_5_template_sizes():
    frame = np.random.uniform(0, 255, (240, 320, 3)).astype(np.uint8)
    landmarks = np.array([
        [100, 80], [150, 80], [125, 110], [105, 140], [145, 140]
    ], np.float32)
    sizes = {"arcface_112_v1": 112, "arcface_112_v2": 112, "arcface_128": 128}
    for template_name in WARP_TEMPLATE_SET:
        side = sizes[template_name]
        crop, matrix = warp_face_by_face_landmark_5(
            frame, landmarks, template_name, (side, side))
        assert crop.shape == (side, side, 3), (template_name, crop.shape)
        assert matrix is not None and matrix.shape == (2, 3)


def test_paste_back_roundtrip():
    from app.ffcompat import estimate_matrix_by_face_landmark_5
    frame = np.full((400, 400, 3), 128, np.uint8)
    size = 112
    frame_landmarks = np.array([
        [200, 150], [250, 145], [225, 190], [205, 230], [245, 228]
    ], np.float32)
    affine = estimate_matrix_by_face_landmark_5(
        frame_landmarks, "arcface_112_v1", (size, size))
    assert affine is not None and affine.shape == (2, 3)

    crop = np.full((size, size, 3), 255, np.float32)
    mask = np.ones((size, size), np.float32)
    out = paste_back(frame, crop, mask, affine)
    assert out.shape == frame.shape
    assert not np.allclose(out, frame)  # paste actually happened
    # deterministic: same inputs -> same output
    assert np.array_equal(out, paste_back(frame, crop, mask, affine))


def test_create_box_mask_padding_blur():
    frame = np.zeros((256, 256, 3), np.uint8)
    mask = create_box_mask(frame, 0.25, (10, 10, 10, 10))
    assert mask.shape == (256, 256)
    assert 0 < mask.sum() < 256 * 256   # feathered, not solid
    center = mask[96:160, 96:160]
    assert np.allclose(center, 1.0), "center of box mask must be fully open"


def test_pixel_boost_roundtrip():
    size = 256
    total, model = 2, 128
    rng = np.random.default_rng(42)
    crop = rng.random((size, size, 3)).astype(np.float32)
    tiles = implode_pixel_boost(crop, total, (model, model))
    assert tiles.shape == (total ** 2, model, model, 3)
    back = explode_pixel_boost(list(tiles), total, (model, model), (size, size))
    assert back.shape == (size, size, 3)
    assert np.allclose(back, crop), "explode must invert implode exactly"
