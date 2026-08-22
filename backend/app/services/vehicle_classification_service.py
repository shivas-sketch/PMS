"""Refines the coarse YOLO detection category into a useful vehicle type.

Standard COCO-pretrained YOLO can only tell us "car", "motorcycle", "bus",
"truck" or "bicycle" - it cannot distinguish a Sedan from an SUV, or a
Pickup from a Van/Truck. Rather than guessing, this service exposes a
pluggable refinement hook per coarse category. Until a dedicated
classifier/model/API is plugged in, it honestly falls back to the generic
label (e.g. "Car") instead of fabricating a confident Sedan/SUV/Hatchback
answer.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Canonical display labels the API is allowed to return.
VEHICLE_TYPE_LABELS = {
    "bike": "Bike",
    "scooter": "Scooter",
    "auto_rickshaw": "Auto Rickshaw",
    "hatchback": "Hatchback",
    "sedan": "Sedan",
    "suv": "SUV",
    "car": "Car",
    "van": "Van",
    "pickup": "Pickup",
    "truck": "Truck",
    "bus": "Bus",
    "other": "Other",
}

# Coarse detector category -> generic fallback wheel-mapping key.
_COARSE_CATEGORY_TO_WHEEL_KEY: Dict[str, str] = {
    "bicycle": "bike",
    "motorcycle": "bike",
    "car": "car",
    "bus": "bus",
    "truck": "truck",
}


@dataclass
class ClassificationResult:
    vehicle_type: str  # canonical display label, e.g. "SUV", "Car"
    wheel_key: str  # key into WHEEL_MAPPING, e.g. "suv", "car"
    confidence: float
    refined: bool  # True if a dedicated sub-classifier produced this, not just a fallback


# A refinement hook receives the cropped vehicle image and must return
# (wheel_key, confidence) or None when it cannot confidently refine further.
RefinerFn = Callable[[np.ndarray], Optional[tuple[str, float]]]


class VehicleClassificationService:
    def __init__(self, classifier_model_path: str = ""):
        self.classifier_model_path = classifier_model_path
        self._car_refiner: Optional[RefinerFn] = None
        self._truck_refiner: Optional[RefinerFn] = None
        self._two_wheeler_refiner: Optional[RefinerFn] = None
        self._loaded = False

    def load(self) -> None:
        """Attempt to load an optional dedicated sub-classifier.

        No bundled model ships with this POC, so by default this is a
        no-op and every refiner stays ``None`` (i.e. the service is honest
        about only knowing the coarse category). Replace this method to
        wire in a real model/external API without changing any caller.
        """
        if self._loaded:
            return
        self._loaded = True
        if not self.classifier_model_path:
            logger.info(
                "VehicleClassificationService: no classifier configured, "
                "falling back to generic labels (Car/Truck/Bike)."
            )
            return
        logger.info(
            "VehicleClassificationService: classifier path '%s' configured but no "
            "loader is implemented yet; keeping fallback behaviour.",
            self.classifier_model_path,
        )

    def classify(
        self,
        vehicle_crop: Optional[np.ndarray],
        coarse_category: Optional[str],
        detection_confidence: float,
    ) -> ClassificationResult:
        if not self._loaded:
            self.load()

        if coarse_category is None:
            return ClassificationResult(
                vehicle_type=VEHICLE_TYPE_LABELS["other"],
                wheel_key="other",
                confidence=detection_confidence,
                refined=False,
            )

        wheel_key = _COARSE_CATEGORY_TO_WHEEL_KEY.get(coarse_category, "other")
        refiner = self._refiner_for(coarse_category)

        if refiner is not None and vehicle_crop is not None:
            refined = refiner(vehicle_crop)
            if refined is not None:
                refined_key, refined_confidence = refined
                return ClassificationResult(
                    vehicle_type=VEHICLE_TYPE_LABELS.get(refined_key, VEHICLE_TYPE_LABELS["other"]),
                    wheel_key=refined_key,
                    confidence=refined_confidence,
                    refined=True,
                )

        # Honest fallback: we only know the coarse category, so we return
        # the generic label rather than pretending to know Sedan/SUV/etc.
        return ClassificationResult(
            vehicle_type=VEHICLE_TYPE_LABELS.get(wheel_key, VEHICLE_TYPE_LABELS["other"]),
            wheel_key=wheel_key,
            confidence=detection_confidence,
            refined=False,
        )

    def _refiner_for(self, coarse_category: str) -> Optional[RefinerFn]:
        if coarse_category == "car":
            return self._car_refiner
        if coarse_category == "truck":
            return self._truck_refiner
        if coarse_category in ("motorcycle", "bicycle"):
            return self._two_wheeler_refiner
        return None
