"""OCR over a cropped, in-memory plate image.

PaddleOCR is the preferred engine; EasyOCR is used as an automatic
fallback if PaddleOCR cannot be imported/initialized in the current
environment (e.g. paddlepaddle not installed). If neither engine is
available the service degrades gracefully and reports "unavailable"
rather than crashing the request.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class OCRResult:
    text: str
    confidence: float
    engine: str  # "paddleocr" | "easyocr" | "unavailable"


class OCRService:
    def __init__(self, preferred_engine: str = "paddleocr", languages: str = "en"):
        self.preferred_engine = preferred_engine
        self.languages = languages
        self._reader = None
        self._backend: Optional[str] = None
        self._load_attempted = False

    def load(self) -> None:
        if self._load_attempted:
            return
        self._load_attempted = True

        engines = ["paddleocr", "easyocr"]
        if self.preferred_engine in engines:
            engines.remove(self.preferred_engine)
            engines.insert(0, self.preferred_engine)

        for engine in engines:
            if engine == "paddleocr" and self._try_load_paddleocr():
                return
            if engine == "easyocr" and self._try_load_easyocr():
                return

        logger.warning("OCRService: no OCR engine could be initialized; OCR will be skipped.")
        self._backend = "unavailable"

    def _try_load_paddleocr(self) -> bool:
        try:
            from paddleocr import PaddleOCR

            try:
                self._reader = PaddleOCR(use_angle_cls=True, lang=self.languages, show_log=False)
            except TypeError:
                # Newer PaddleOCR releases dropped some legacy kwargs.
                self._reader = PaddleOCR(lang=self.languages)
            self._backend = "paddleocr"
            logger.info("OCRService: PaddleOCR engine ready")
            return True
        except Exception as exc:  # pragma: no cover
            logger.warning("OCRService: PaddleOCR unavailable (%s)", exc)
            return False

    def _try_load_easyocr(self) -> bool:
        try:
            import easyocr

            langs = [lang.strip() for lang in self.languages.split(",") if lang.strip()] or ["en"]
            self._reader = easyocr.Reader(langs, gpu=False)
            self._backend = "easyocr"
            logger.info("OCRService: EasyOCR engine ready (fallback)")
            return True
        except Exception as exc:  # pragma: no cover
            logger.warning("OCRService: EasyOCR unavailable (%s)", exc)
            return False

    @property
    def is_available(self) -> bool:
        return self._backend not in (None, "unavailable")

    def read_plate(self, plate_image: np.ndarray) -> OCRResult:
        if not self._load_attempted:
            self.load()

        if self._backend not in ("paddleocr", "easyocr"):
            return OCRResult(text="", confidence=0.0, engine="unavailable")

        variants = _generate_ocr_variants(plate_image)
        results: List[OCRResult] = []
        for label, variant in variants:
            if self._backend == "paddleocr":
                r = self._read_with_paddleocr(variant)
            else:
                r = self._read_with_easyocr(variant)
            if r.text:
                logger.info(
                    "OCRService: variant=%s raw_text=%r confidence=%.3f",
                    label, r.text, r.confidence,
                )
                results.append(r)

        if not results:
            return OCRResult(text="", confidence=0.0, engine=self._backend or "unavailable")

        # Prefer results that look like a plate (alphanumeric, 8-11 chars).
        # Among those, pick highest confidence.
        plate_like = [r for r in results if _looks_like_plate(r.text)]
        if plate_like:
            plate_like.sort(key=lambda r: r.confidence, reverse=True)
            return plate_like[0]

        results.sort(key=lambda r: r.confidence, reverse=True)
        return results[0]

    def _read_with_paddleocr(self, plate_image: np.ndarray) -> OCRResult:
        try:
            raw = self._reader.ocr(plate_image, cls=True)
        except TypeError:
            raw = self._reader.ocr(plate_image)
        except Exception as exc:  # pragma: no cover
            logger.warning("OCRService: PaddleOCR inference failed (%s)", exc)
            return OCRResult(text="", confidence=0.0, engine="paddleocr")

        tokens = _parse_paddleocr_result(raw)
        return _combine_tokens_row_aware(tokens, "paddleocr")

    def _read_with_easyocr(self, plate_image: np.ndarray) -> OCRResult:
        try:
            raw = self._reader.readtext(plate_image)
        except Exception as exc:  # pragma: no cover
            logger.warning("OCRService: EasyOCR inference failed (%s)", exc)
            return OCRResult(text="", confidence=0.0, engine="easyocr")

        tokens: List[Tuple[float, float, str, float]] = []
        for entry in raw or []:
            try:
                box, text, conf = entry
                min_x = min(point[0] for point in box)
                min_y = min(point[1] for point in box)
                tokens.append((float(min_x), float(min_y), str(text), float(conf)))
            except Exception:  # pragma: no cover
                continue
        return _combine_tokens_row_aware(tokens, "easyocr")


def _parse_paddleocr_result(raw) -> List[Tuple[float, float, str, float]]:
    """Defensively parse PaddleOCR's output across SDK versions.

    Expected shape is ``[[ [box, (text, conf)], ... ]]`` (one entry per
    input image), but some versions return the inner list directly for a
    single image, or dict-based results. We handle the common cases and
    otherwise return no tokens rather than raising.

    Returns tokens as ``(min_x, min_y, text, confidence)`` so callers can
    reconstruct multi-line plates by grouping rows.
    """
    tokens: List[Tuple[float, float, str, float]] = []
    if not raw:
        return tokens

    lines = raw[0] if isinstance(raw, list) and raw and isinstance(raw[0], list) else raw

    for line in lines or []:
        try:
            box, text_conf = line
            text, conf = text_conf
            min_x = min(point[0] for point in box)
            min_y = min(point[1] for point in box)
            tokens.append((float(min_x), float(min_y), str(text), float(conf)))
        except Exception:
            continue
    return tokens


def _combine_tokens_row_aware(tokens: List[Tuple[float, float, str, float]], engine: str) -> OCRResult:
    """Combine OCR tokens into a single string, preserving multi-row layout.

    Groups tokens by their vertical position into rows, sorts each row
    left-to-right, then joins rows top-to-bottom. This is essential for
    two-line Indian plates where the number appears below the state code.
    """
    if not tokens:
        return OCRResult(text="", confidence=0.0, engine=engine)

    # Group tokens into rows by their y-coordinate using a simple threshold.
    # Sort by y, then group when the gap between consecutive y's is small.
    tokens_by_y = sorted(tokens, key=lambda t: t[1])
    # Use median token height as row threshold; fall back to 10px.
    ys = [t[1] for t in tokens]
    if len(ys) >= 2:
        y_range = max(ys) - min(ys)
        row_threshold = max(10, y_range * 0.15)
    else:
        row_threshold = 10

    rows: List[List[Tuple[float, float, str, float]]] = []
    current_row = [tokens_by_y[0]]
    for token in tokens_by_y[1:]:
        if abs(token[1] - current_row[-1][1]) <= row_threshold:
            current_row.append(token)
        else:
            rows.append(current_row)
            current_row = [token]
    rows.append(current_row)

    # Sort each row left-to-right and join.
    row_texts = []
    total_conf = 0.0
    total_count = 0
    for row in rows:
        row_sorted = sorted(row, key=lambda t: t[0])
        row_texts.append("".join(t[2] for t in row_sorted))
        total_conf += sum(t[3] for t in row_sorted)
        total_count += len(row_sorted)

    text = "".join(row_texts)
    confidence = total_conf / total_count if total_count else 0.0
    return OCRResult(text=text, confidence=confidence, engine=engine)


def _looks_like_plate(text: str) -> bool:
    """Heuristic: alphanumeric, 8-11 chars after stripping spaces/separators."""
    import re
    cleaned = re.sub(r"[^A-Z0-9]", "", text.upper())
    return 8 <= len(cleaned) <= 11 and bool(re.match(r"^[A-Z0-9]+$", cleaned))


def _generate_ocr_variants(plate_image: np.ndarray) -> List[Tuple[str, np.ndarray]]:
    """Generate multiple preprocessing variants of the plate crop for OCR.

    Different plates respond better to different preprocessing — trying
    several and picking the best result dramatically improves accuracy.

    The variants are ordered roughly from least to most aggressive so the
    OCR engine sees the cleanest images first.
    """
    variants: List[Tuple[str, np.ndarray]] = []
    h, w = plate_image.shape[:2]
    is_color = len(plate_image.shape) == 3

    # 1. Original image as-is (PaddleOCR has its own preprocessing)
    variants.append(("original", plate_image))

    # 2. Upscaled 2x with Lanczos for better edge preservation
    if min(h, w) < 120:
        upscaled2 = cv2.resize(plate_image, (w * 2, h * 2), interpolation=cv2.INTER_LANCZOS4)
        variants.append(("upscaled2x", upscaled2))
    else:
        upscaled2 = plate_image

    # 3. Upscaled 3x for very small plates
    if min(h, w) < 60:
        upscaled3 = cv2.resize(plate_image, (w * 3, h * 3), interpolation=cv2.INTER_LANCZOS4)
        variants.append(("upscaled3x", upscaled3))

    # Grayscale base for processing
    gray = cv2.cvtColor(plate_image, cv2.COLOR_BGR2GRAY) if is_color else plate_image

    # 4. Grayscale + CLAHE contrast enhancement (stronger)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
    contrast = clahe.apply(gray)
    variants.append(("clahe", contrast))

    # 5. Grayscale + Otsu threshold (binary image)
    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(("otsu", otsu))

    # 6. Grayscale + adaptive threshold
    adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 5)
    variants.append(("adaptive", adaptive))

    # 7. Grayscale + bilateral filter (edge-preserving denoise) + CLAHE
    bilateral = cv2.bilateralFilter(gray, 9, 75, 75)
    bilateral_clahe = clahe.apply(bilateral)
    variants.append(("bilateral_clahe", bilateral_clahe))

    # 8. Grayscale + denoise + unsharp mask
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    blurred = cv2.GaussianBlur(denoised, (0, 0), 1.0)
    unsharped = cv2.addWeighted(denoised, 2.0, blurred, -1.0, 0)
    variants.append(("denoise_unsharp", unsharped))

    # 9. Upscaled 2x + CLAHE
    if min(h, w) < 120:
        up_gray = cv2.cvtColor(upscaled2, cv2.COLOR_BGR2GRAY) if len(upscaled2.shape) == 3 else upscaled2
        up_clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
        up_contrast = up_clahe.apply(up_gray)
        variants.append(("upscaled_clahe", up_contrast))

    # 10. Upscaled 2x + Otsu
    if min(h, w) < 120:
        up_gray_otsu = cv2.cvtColor(upscaled2, cv2.COLOR_BGR2GRAY) if len(upscaled2.shape) == 3 else upscaled2
        _, up_otsu = cv2.threshold(up_gray_otsu, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        variants.append(("upscaled_otsu", up_otsu))

    # 11. Upscaled 2x + denoise + unsharp mask
    if min(h, w) < 120:
        up_gray2 = cv2.cvtColor(upscaled2, cv2.COLOR_BGR2GRAY) if len(upscaled2.shape) == 3 else upscaled2
        up_denoised = cv2.fastNlMeansDenoising(up_gray2, h=10)
        up_blurred = cv2.GaussianBlur(up_denoised, (0, 0), 1.0)
        up_unsharped = cv2.addWeighted(up_denoised, 2.0, up_blurred, -1.0, 0)
        variants.append(("upscaled_unsharp", up_unsharped))

    # 12. CLAHE + Otsu (contrast enhancement then binarize)
    _, contrast_otsu = cv2.threshold(contrast, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(("clahe_otsu", contrast_otsu))

    # 13. Glow removal: morphological open to suppress halos
    glow_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    opened = cv2.morphologyEx(gray, cv2.MORPH_OPEN, glow_kernel)
    variants.append(("glow_open", opened))

    # 14. Black-hat transform: enhances dark text on bright/reflective background
    blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, glow_kernel)
    variants.append(("blackhat", blackhat))

    # 15. Inverted image (for plates where text appears dark on light)
    inverted = cv2.bitwise_not(gray)
    variants.append(("inverted", inverted))

    # 16. Local threshold using smaller block (good for uneven lighting)
    local_threshold = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 7)
    variants.append(("adaptive_small", local_threshold))

    # 17. Bilateral + Otsu (edge-preserving denoise then binarize)
    _, bilateral_otsu = cv2.threshold(bilateral, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(("bilateral_otsu", bilateral_otsu))

    return variants
