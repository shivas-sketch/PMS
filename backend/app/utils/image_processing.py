"""Pure in-memory image helpers.

Nothing in this module ever writes to disk. Images only ever exist as
NumPy arrays / raw bytes held in local variables for the lifetime of a
single request.
"""
from __future__ import annotations

import gc
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

import cv2
import numpy as np

from app.config.settings import Settings


class InvalidImageError(ValueError):
    """Raised when an uploaded file is not a decodable/allowed image."""


@dataclass(frozen=True)
class BoundingBox:
    x1: int
    y1: int
    x2: int
    y2: int

    def clipped(self, width: int, height: int) -> "BoundingBox":
        return BoundingBox(
            x1=max(0, min(self.x1, width - 1)),
            y1=max(0, min(self.y1, height - 1)),
            x2=max(0, min(self.x2, width)),
            y2=max(0, min(self.y2, height)),
        )

    @property
    def as_tuple(self) -> tuple[int, int, int, int]:
        return self.x1, self.y1, self.x2, self.y2


def validate_upload(content_type: Optional[str], size_bytes: int, settings: Settings) -> None:
    """Validate content-type and size before any decoding happens."""
    if size_bytes <= 0:
        raise InvalidImageError("Uploaded file is empty")

    if size_bytes > settings.max_upload_size_bytes:
        raise InvalidImageError(
            f"Image exceeds the maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB} MB"
        )

    if content_type not in settings.allowed_content_types:
        raise InvalidImageError(
            f"Unsupported content type '{content_type}'. Allowed: {sorted(settings.allowed_content_types)}"
        )


def bytes_to_image(image_bytes: bytes) -> np.ndarray:
    """Decode raw bytes straight into an OpenCV BGR array. Never touches disk."""
    np_array = np.frombuffer(image_bytes, np.uint8)
    frame = cv2.imdecode(np_array, cv2.IMREAD_COLOR)
    if frame is None:
        raise InvalidImageError("Uploaded file could not be decoded as an image")
    return frame


def crop_region(image: np.ndarray, box: BoundingBox, margin_ratio: float = 0.0) -> np.ndarray:
    """Return a copy of the pixels inside ``box`` (with optional margin), clipped to bounds."""
    height, width = image.shape[:2]
    if margin_ratio:
        mw = int((box.x2 - box.x1) * margin_ratio)
        mh = int((box.y2 - box.y1) * margin_ratio)
        box = BoundingBox(box.x1 - mw, box.y1 - mh, box.x2 + mw, box.y2 + mh)
    box = box.clipped(width, height)
    x1, y1, x2, y2 = box.as_tuple
    if x2 <= x1 or y2 <= y1:
        raise InvalidImageError("Computed crop region is empty")
    return image[y1:y2, x1:x2].copy()


def resize_min_side(image: np.ndarray, min_side: int = 64) -> np.ndarray:
    """Upscale small crops so OCR has enough resolution to work with."""
    h, w = image.shape[:2]
    shortest = min(h, w)
    if shortest == 0:
        raise InvalidImageError("Cannot resize an empty image")
    if shortest >= min_side:
        return image
    scale = min_side / float(shortest)
    return cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)


def upscale_plate(image: np.ndarray, target_height: int = 128) -> np.ndarray:
    """Upscale a plate crop so its height is at least ``target_height`` pixels.

    Uses INTER_LANCZOS4 for highest-quality upscaling, which preserves
    character edge sharpness better than INTER_CUBIC for small plates.
    """
    h, w = image.shape[:2]
    if h == 0 or w == 0:
        raise InvalidImageError("Cannot resize an empty image")
    if h >= target_height:
        return image
    scale = target_height / float(h)
    new_w = int(w * scale)
    new_h = int(h * scale)
    return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)


def to_grayscale(image: np.ndarray) -> np.ndarray:
    if len(image.shape) == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def enhance_contrast(gray: np.ndarray) -> np.ndarray:
    """CLAHE-based local contrast enhancement. Mild by design."""
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def sharpen(gray: np.ndarray) -> np.ndarray:
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    return cv2.filter2D(gray, -1, kernel)


def denoise(gray: np.ndarray) -> np.ndarray:
    return cv2.fastNlMeansDenoising(gray, h=10)


def unsharp_mask(gray: np.ndarray, sigma: float = 1.0, strength: float = 1.5) -> np.ndarray:
    """Unsharp mask: sharpen edges without amplifying noise.

    Blurs the image with a Gaussian, then adds the difference back to the
    original. More controllable than a simple kernel-based sharpen.
    """
    blurred = cv2.GaussianBlur(gray, (0, 0), sigma)
    sharpened = cv2.addWeighted(gray, 1.0 + strength, blurred, -strength, 0)
    return sharpened


def deskew(image: np.ndarray, max_angle: float = 15.0) -> np.ndarray:
    """Correct small rotational skew in a plate crop.

    Uses the minAreaRect of all non-zero pixels to estimate the rotation
    angle, then rotates the image to make the text horizontal. Only
    corrects angles up to ``max_angle`` degrees to avoid over-correcting.
    """
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    # Threshold to get text pixels
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = np.column_stack(np.where(binary > 0))
    if len(coords) < 10:
        return image

    angle = cv2.minAreaRect(coords)[-1]
    # minAreaRect returns angle in [-90, 0). Normalize to [-45, 45).
    if angle < -45:
        angle = 90 + angle

    if abs(angle) > max_angle or abs(angle) < 0.1:
        return image

    h, w = image.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(image, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def remove_borders(image: np.ndarray, border_threshold: int = 200) -> np.ndarray:
    """Remove white or dark borders around a plate crop.

    Borders (screw heads, plate frame, background) can confuse OCR.
    Crops rows/columns from each edge that are predominantly above
    ``border_threshold`` (white) or below ``50`` (dark).
    """
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    h, w = gray.shape[:2]
    if h < 10 or w < 10:
        return image

    # Compute row and column means
    row_means = gray.mean(axis=1)
    col_means = gray.mean(axis=0)

    # Find first/last rows that contain actual text (not border)
    text_rows = np.where((row_means > 50) & (row_means < border_threshold))[0]
    text_cols = np.where((col_means > 50) & (col_means < border_threshold))[0]

    if len(text_rows) == 0 or len(text_cols) == 0:
        return image

    top = max(0, text_rows[0] - 1)
    bottom = min(h, text_rows[-1] + 2)
    left = max(0, text_cols[0] - 1)
    right = min(w, text_cols[-1] + 2)

    # Only crop if we're removing less than 40% of the image
    if (bottom - top) < h * 0.6 or (right - left) < w * 0.6:
        return image

    return image[top:bottom, left:right].copy()


def adaptive_threshold(gray: np.ndarray) -> np.ndarray:
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 7
    )


def enhance_plate_image(
    plate_image: np.ndarray,
    steps: Sequence[str] = ("upscale", "deskew", "remove_borders", "grayscale", "contrast", "denoise", "unsharp_mask"),
) -> np.ndarray:
    """Apply a configurable enhancement chain before OCR.

    Defaults use a stronger pipeline than before:
    - ``upscale``: Lanczos upscaling to ensure at least 128px height
    - ``deskew``: correct small rotational skew
    - ``remove_borders``: crop white/dark borders that confuse OCR
    - ``grayscale``: convert to grayscale
    - ``contrast``: CLAHE local contrast enhancement
    - ``denoise``: non-local means denoising
    - ``unsharp_mask``: edge sharpening via unsharp mask
    """
    result = plate_image
    for step in steps:
        if step == "resize":
            result = resize_min_side(result, min_side=64)
        elif step == "upscale":
            result = upscale_plate(result, target_height=128)
        elif step == "deskew":
            result = deskew(result)
        elif step == "remove_borders":
            result = remove_borders(result)
        elif step == "grayscale":
            result = to_grayscale(result)
        elif step == "contrast":
            result = enhance_contrast(to_grayscale(result) if len(result.shape) == 3 else result)
        elif step == "sharpen":
            result = sharpen(to_grayscale(result) if len(result.shape) == 3 else result)
        elif step == "unsharp_mask":
            g = to_grayscale(result) if len(result.shape) == 3 else result
            result = unsharp_mask(g)
        elif step == "denoise":
            result = denoise(to_grayscale(result) if len(result.shape) == 3 else result)
        elif step == "threshold":
            result = adaptive_threshold(to_grayscale(result) if len(result.shape) == 3 else result)
    return result


def correct_perspective(plate_image: np.ndarray) -> np.ndarray:
    """Attempt perspective (skew) correction on a plate crop.

    Uses OpenCV contour detection to find the plate's quadrilateral corners,
    then warps it into a rectified front-on view. If no good quadrilateral is
    found, returns the original image unchanged.
    """
    h, w = plate_image.shape[:2]
    if len(plate_image.shape) == 3:
        gray = cv2.cvtColor(plate_image, cv2.COLOR_BGR2GRAY)
    else:
        gray = plate_image

    gray = cv2.bilateralFilter(gray, 11, 17, 17)
    edges = cv2.Canny(gray, 30, 200)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]

    quad = None
    for contour in contours:
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
        if len(approx) == 4:
            area = cv2.contourArea(approx)
            if area > 0.3 * w * h:
                quad = approx
                break

    if quad is None:
        return plate_image

    pts = quad.reshape(4, 2).astype(np.float32)
    rect = _order_corners(pts)

    width_top = np.linalg.norm(rect[0] - rect[1])
    width_bottom = np.linalg.norm(rect[2] - rect[3])
    height_left = np.linalg.norm(rect[0] - rect[3])
    height_right = np.linalg.norm(rect[1] - rect[2])

    max_width = int(max(width_top, width_bottom))
    max_height = int(max(height_left, height_right))

    if max_width < 20 or max_height < 10:
        return plate_image

    dst = np.array([
        [0, 0],
        [max_width - 1, 0],
        [max_width - 1, max_height - 1],
        [0, max_height - 1],
    ], dtype=np.float32)

    matrix = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(plate_image, matrix, (max_width, max_height))


def _order_corners(pts: np.ndarray) -> np.ndarray:
    """Order 4 corner points as: top-left, top-right, bottom-right, bottom-left."""
    rect = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    d = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(d)]
    rect[3] = pts[np.argmax(d)]
    return rect


def discard(*arrays: Optional[np.ndarray]) -> None:
    """Best-effort explicit release of in-memory image buffers.

    Python cannot un-reference a caller's variable from inside a callee, so
    callers must also ``del`` their local names; this helper exists to make
    the intent explicit at each call site and to force a GC pass so large
    NumPy buffers are freed promptly rather than lingering until the next
    collection cycle.
    """
    del arrays
    gc.collect()
