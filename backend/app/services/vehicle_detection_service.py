"""YOLO-based vehicle detection.

Wraps a maintained Ultralytics YOLO model. The COCO-pretrained weights
(``yolov8n.pt``) already recognise the vehicle categories we care about, so
they are a solid default; swap ``VEHICLE_MODEL_PATH`` for a custom model
later without touching any caller of this service.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from app.utils.image_processing import BoundingBox

logger = logging.getLogger(__name__)

# Ultralytics COCO class indices relevant to vehicle detection.
COCO_VEHICLE_CLASSES: dict[int, str] = {
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}


@dataclass
class VehicleDetection:
    category: str  # raw detector category, e.g. "car", "motorcycle"
    confidence: float
    box: BoundingBox


class VehicleDetectionService:
    """Detects vehicles (car/bus/truck/motorcycle/bicycle) in a frame."""

    def __init__(self, model_path: str = "yolov8n.pt"):
        self.model_path = model_path
        self._model = None
        self._load_error: Optional[str] = None

    def load(self) -> None:
        """Load the YOLO model once. Safe to call multiple times."""
        if self._model is not None or self._load_error is not None:
            return
        try:
            from ultralytics import YOLO

            self._model = YOLO(self.model_path)
            logger.info("VehicleDetectionService: loaded model '%s'", self.model_path)
        except Exception as exc:  # pragma: no cover - exercised via unit tests with fakes
            self._load_error = str(exc)
            logger.warning("VehicleDetectionService: model unavailable (%s). "
                            "Vehicle detection will be skipped until a model is available.", exc)

    @property
    def is_available(self) -> bool:
        return self._model is not None

    def detect(self, image: np.ndarray) -> List[VehicleDetection]:
        """Run detection and return vehicle candidates sorted by confidence desc."""
        if self._model is None:
            self.load()
        if self._model is None:
            return []

        results = self._model(image, verbose=False)
        detections: List[VehicleDetection] = []
        raw_classes: list = []
        for result in results:
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                raw_classes.append((cls_id, round(conf, 3)))
                category = COCO_VEHICLE_CLASSES.get(cls_id)
                if category is None:
                    continue
                confidence = float(box.conf[0])
                x1, y1, x2, y2 = (float(v) for v in box.xyxy[0])
                detections.append(
                    VehicleDetection(
                        category=category,
                        confidence=confidence,
                        box=BoundingBox(int(x1), int(y1), int(x2), int(y2)),
                    )
                )

        if not detections:
            logger.info(
                "VehicleDetectionService: no vehicle classes found. raw_yolo_detections=%s",
                raw_classes,
            )

        detections.sort(key=lambda d: d.confidence, reverse=True)
        return detections

    def detect_best(self, image: np.ndarray) -> Optional[VehicleDetection]:
        detections = self.detect(image)
        return detections[0] if detections else None
