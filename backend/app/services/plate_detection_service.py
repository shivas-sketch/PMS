"""Number-plate localization.

Preferred path: a pretrained YOLO license-plate detector, path configurable
via ``LICENSE_PLATE_MODEL_PATH``. COCO-pretrained YOLO has no "license
plate" class, so when no dedicated model is configured/available this
service falls back to a classic OpenCV contour/edge heuristic. The
heuristic is intentionally capped at a modest confidence so downstream
consumers never mistake it for a strong detection.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import List, Optional

import cv2
import numpy as np

from app.utils.image_processing import BoundingBox

logger = logging.getLogger(__name__)

HEURISTIC_MAX_CONFIDENCE = 0.55


@dataclass
class PlateDetection:
    confidence: float
    box: BoundingBox
    method: str  # "yolo" | "heuristic"


class NumberPlateDetectionService:
    def __init__(self, model_path: str = ""):
        self.model_path = model_path
        self._model = None
        self._load_attempted = False

    def load(self) -> None:
        if self._load_attempted:
            return
        self._load_attempted = True
        if not self.model_path or not os.path.exists(self.model_path):
            logger.info(
                "NumberPlateDetectionService: no LICENSE_PLATE_MODEL_PATH configured/found "
                "(%s); using OpenCV heuristic fallback.",
                self.model_path or "<unset>",
            )
            return
        try:
            from ultralytics import YOLO

            self._model = YOLO(self.model_path)
            logger.info("NumberPlateDetectionService: loaded model '%s'", self.model_path)
        except Exception as exc:  # pragma: no cover
            logger.warning("NumberPlateDetectionService: failed to load model (%s); using heuristic.", exc)

    @property
    def is_model_available(self) -> bool:
        return self._model is not None

    def detect_plate(self, image: np.ndarray) -> Optional[PlateDetection]:
        if not self._load_attempted:
            self.load()

        if self._model is not None:
            detection = self._detect_with_model(image)
            if detection is not None:
                return detection

        return self._detect_heuristic(image)

    def detect_plates(self, image: np.ndarray, top_k: int = 3) -> List[PlateDetection]:
        """Return up to top_k plate detections sorted by confidence desc."""
        if not self._load_attempted:
            self.load()

        if self._model is not None:
            detections = self._detect_all_with_model(image)
            if detections:
                return detections[:top_k]

        heuristic = self._detect_heuristic(image)
        return [heuristic] if heuristic else []

    def _detect_all_with_model(self, image: np.ndarray) -> List[PlateDetection]:
        results = self._model(image, verbose=False)
        candidates: List[PlateDetection] = []
        for result in results:
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:
                confidence = float(box.conf[0])
                x1, y1, x2, y2 = (float(v) for v in box.xyxy[0])
                candidates.append(
                    PlateDetection(
                        confidence=confidence,
                        box=BoundingBox(int(x1), int(y1), int(x2), int(y2)),
                        method="yolo",
                    )
                )
        candidates.sort(key=lambda c: c.confidence, reverse=True)
        return candidates

    def _detect_with_model(self, image: np.ndarray) -> Optional[PlateDetection]:
        results = self._model(image, verbose=False)
        candidates: List[PlateDetection] = []
        for result in results:
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:
                confidence = float(box.conf[0])
                x1, y1, x2, y2 = (float(v) for v in box.xyxy[0])
                candidates.append(
                    PlateDetection(
                        confidence=confidence,
                        box=BoundingBox(int(x1), int(y1), int(x2), int(y2)),
                        method="yolo",
                    )
                )
        if not candidates:
            return None
        candidates.sort(key=lambda c: c.confidence, reverse=True)
        return candidates[0]

    def _detect_heuristic(self, image: np.ndarray) -> Optional[PlateDetection]:
        """Classic edge/contour based plate localization.

        Looks for a rectangular, plate-shaped contour (wide aspect ratio)
        in the lower portion of the image, which is where plates usually
        sit on a vehicle-cropped photo. Also allows a close-up plate that
        fills a large fraction of the frame.
        """
        try:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            gray = cv2.bilateralFilter(gray, 11, 17, 17)
            edges = cv2.Canny(gray, 30, 200)
            contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

            height, width = gray.shape[:2]
            image_area = float(height * width)
            best_box: Optional[BoundingBox] = None
            best_score = 0.0

            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                if h == 0:
                    continue
                aspect_ratio = w / float(h)
                area_ratio = (w * h) / image_area

                # Plates are wide rectangles; allow very close-up shots where
                # the plate may dominate the image.
                if not (1.8 <= aspect_ratio <= 8.0):
                    continue
                if not (0.003 <= area_ratio <= 0.95):
                    continue

                vertical_bias = y / float(height)  # plates tend to sit lower
                # For close-up plates, de-emphasize vertical bias.
                if area_ratio > 0.5:
                    score = area_ratio
                else:
                    score = area_ratio * (0.5 + vertical_bias)
                if score > best_score:
                    best_score = score
                    best_box = BoundingBox(x, y, x + w, y + h)

            if best_box is None:
                logger.info("NumberPlateDetectionService: heuristic found no plate")
                return None

            confidence = min(HEURISTIC_MAX_CONFIDENCE, 0.30 + best_score)
            logger.info(
                "NumberPlateDetectionService: heuristic plate found box=%s conf=%.3f",
                best_box, confidence,
            )
            return PlateDetection(confidence=confidence, box=best_box, method="heuristic")
        except Exception as exc:  # pragma: no cover
            logger.warning("NumberPlateDetectionService: heuristic detection failed (%s)", exc)
            return None
