"""
Post-processing filters for PixelMorph.
Lightweight OpenCV-based enhancements designed for real-time (sub-5ms) use.
"""

import cv2
import numpy as np

from app.logger import get_logger

log = get_logger(__name__)


def apply_clahe(frame: np.ndarray, clip_limit: float = 2.0,
                grid_size: int = 8) -> np.ndarray:
    """Contrast Limited Adaptive Histogram Equalization on L-channel.

    Fixes poor webcam contrast/lighting.  Fast (~1ms at 720p).
    """
    if frame is None or frame.size == 0:
        return frame
    try:
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=clip_limit,
                                tileGridSize=(grid_size, grid_size))
        l = clahe.apply(l)
        lab = cv2.merge([l, a, b])
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    except Exception as e:
        log.warning("CLAHE filter error: %s", e)
        return frame


def apply_sharpen(frame: np.ndarray, strength: float = 0.5) -> np.ndarray:
    """Unsharp masking — makes output crisp without over-sharpening.

    Uses Gaussian blur as the smoothed version for the unsharp mask.
    """
    if frame is None or frame.size == 0:
        return frame
    try:
        blurred = cv2.GaussianBlur(frame, (0, 0), 1.0)
        sharpened = cv2.addWeighted(frame, 1.0 + strength,
                                    blurred, -strength, 0)
        return np.clip(sharpened, 0, 255).astype(np.uint8)
    except Exception as e:
        log.warning("Sharpen filter error: %s", e)
        return frame


def apply_white_balance(frame: np.ndarray, strength: float = 0.5) -> np.ndarray:
    """Gray-world auto white balance.

    Assumes the average scene color is gray, then scales each channel
    to correct color casts from bad lighting.
    """
    if frame is None or frame.size == 0:
        return frame
    try:
        result = frame.astype(np.float32)
        mean_b = float(np.mean(result[:, :, 0]))
        mean_g = float(np.mean(result[:, :, 1]))
        mean_r = float(np.mean(result[:, :, 2]))
        mean_gray = (mean_b + mean_g + mean_r) / 3.0

        eps = 1e-6
        if mean_b > eps:
            result[:, :, 0] *= mean_gray / mean_b
        if mean_g > eps:
            result[:, :, 1] *= mean_gray / mean_g
        if mean_r > eps:
            result[:, :, 2] *= mean_gray / mean_r

        result = np.clip(result, 0, 255).astype(np.uint8)

        if strength < 1.0:
            result = cv2.addWeighted(frame, 1.0 - strength,
                                     result, strength, 0)
        return result
    except Exception as e:
        log.warning("White balance filter error: %s", e)
        return frame


def apply_color_match(swapped: np.ndarray, reference: np.ndarray,
                      strength: float = 0.7) -> np.ndarray:
    """Reinhard LAB colour transfer — match swapped face to scene lighting.

    Fixes the 'sticker effect' where the AI-generated face has different
    colour temperature / lighting than the surrounding video.

    Works in LAB space: aligns mean & std of each channel of *swapped*
    to those of *reference*, then blends by *strength*.
    """
    if swapped is None or reference is None:
        return swapped
    if swapped.size == 0 or reference.size == 0:
        return swapped
    try:
        # Resize reference to match swapped if needed
        ref = reference
        if ref.shape[:2] != swapped.shape[:2]:
            ref = cv2.resize(ref, (swapped.shape[1], swapped.shape[0]),
                             interpolation=cv2.INTER_LINEAR)

        swapped_lab = cv2.cvtColor(swapped, cv2.COLOR_BGR2LAB).astype(np.float32)
        ref_lab = cv2.cvtColor(ref, cv2.COLOR_BGR2LAB).astype(np.float32)

        for c in range(3):
            src_mean = float(np.mean(swapped_lab[:, :, c]))
            src_std = float(np.std(swapped_lab[:, :, c]))
            dst_mean = float(np.mean(ref_lab[:, :, c]))
            dst_std = float(np.std(ref_lab[:, :, c]))

            if src_std > 1e-6 and dst_std > 1e-6:
                scaled = (swapped_lab[:, :, c] - src_mean) * (dst_std / src_std) + dst_mean
                swapped_lab[:, :, c] = np.clip(scaled, 0, 255)

        matched = cv2.cvtColor(swapped_lab.astype(np.uint8), cv2.COLOR_LAB2BGR)

        if strength < 1.0:
            matched = cv2.addWeighted(swapped, 1.0 - strength,
                                      matched, strength, 0)
        return np.clip(matched, 0, 255).astype(np.uint8)
    except Exception as e:
        log.warning("Color match filter error: %s", e)
        return swapped
