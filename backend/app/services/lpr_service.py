"""LPR inference service: YOLO detection + LPRNet recognition.

Replaces the PaddleOCR-based pipeline with a custom-trained end-to-end
model. Loads both models once at startup and provides a simple
`recognize_plate(image)` API.

Usage in the recognition pipeline:
    from app.services.lpr_service import LPRService
    lpr = LPRService(
        detection_model_path="models/plate_model/license_plate.pt",
        recognition_model_path="models/plate_model/lprnet.pth",
    )
    lpr.load()
    result = lpr.recognize_plate(image)
    # result.text = "TN09BK1883", result.confidence = 0.95
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import List, Optional

import cv2
import numpy as np

from app.utils.image_processing import BoundingBox, crop_region, upscale_plate

logger = logging.getLogger(__name__)


@dataclass
class LPRResult:
    text: str
    confidence: float
    box: Optional[BoundingBox] = None
    method: str = "lprnet"


class LPRService:
    """End-to-end license plate recognition using YOLO + LPRNet."""

    def __init__(
        self,
        detection_model_path: str = "",
        recognition_model_path: str = "",
        confidence_threshold: float = 0.5,
    ):
        self.detection_model_path = detection_model_path
        self.recognition_model_path = recognition_model_path
        self.confidence_threshold = confidence_threshold
        self._detector = None
        self._recognizer = None
        self._load_attempted = False

    def load(self) -> None:
        if self._load_attempted:
            return
        self._load_attempted = True

        self._load_detector()
        self._load_recognizer()

    def _load_detector(self) -> None:
        if not self.detection_model_path or not os.path.exists(self.detection_model_path):
            logger.warning("LPRService: detection model not found at %s", self.detection_model_path)
            return
        try:
            from ultralytics import YOLO
            self._detector = YOLO(self.detection_model_path)
            logger.info("LPRService: detection model loaded")
        except Exception as exc:
            logger.warning("LPRService: failed to load detection model (%s)", exc)

    def _load_recognizer(self) -> None:
        if not self.recognition_model_path or not os.path.exists(self.recognition_model_path):
            logger.warning("LPRService: recognition model not found at %s", self.recognition_model_path)
            return
        try:
            import torch
            from training.models.lprnet import LPRNet
            from training.config import NUM_CLASSES, LPR_INPUT_HEIGHT, LPR_INPUT_WIDTH

            self._recognizer = LPRNet(
                num_classes=NUM_CLASSES,
                input_h=LPR_INPUT_HEIGHT,
                input_w=LPR_INPUT_WIDTH,
            )
            state_dict = torch.load(self.recognition_model_path, map_location="cpu")
            self._recognizer.load_state_dict(state_dict)
            self._recognizer.eval()
            logger.info("LPRService: recognition model loaded")
        except Exception as exc:
            logger.warning("LPRService: failed to load recognition model (%s)", exc)

    @property
    def is_available(self) -> bool:
        return self._detector is not None and self._recognizer is not None

    def detect_plates(self, image: np.ndarray, top_k: int = 3) -> List[tuple[float, BoundingBox]]:
        """Detect license plates in an image. Returns list of (confidence, box)."""
        if self._detector is None:
            return []

        results = self._detector(image, verbose=False)
        candidates = []
        for result in results:
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:
                conf = float(box.conf[0])
                if conf < self.confidence_threshold:
                    continue
                x1, y1, x2, y2 = (float(v) for v in box.xyxy[0])
                candidates.append((conf, BoundingBox(int(x1), int(y1), int(x2), int(y2))))

        candidates.sort(key=lambda c: c[0], reverse=True)
        return candidates[:top_k]

    def recognize_plate(self, plate_crop: np.ndarray) -> LPRResult:
        """Recognize text from a cropped plate image using LPRNet."""
        if self._recognizer is None:
            return LPRResult(text="", confidence=0.0)

        import torch
        from training.config import LPR_INPUT_HEIGHT, LPR_INPUT_WIDTH

        # Preprocess: resize to LPRNet input size
        img = cv2.resize(plate_crop, (LPR_INPUT_WIDTH, LPR_INPUT_HEIGHT))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = img.astype(np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1))
        tensor = torch.from_numpy(img).unsqueeze(0)

        text, conf = self._recognizer.predict(tensor)
        return LPRResult(text=text, confidence=conf)

    def recognize(self, image: np.ndarray) -> Optional[LPRResult]:
        """Full pipeline: detect plate → crop → recognize text.

        Args:
            image: Full vehicle image (BGR).

        Returns:
            LPRResult with text, confidence, and bounding box, or None.
        """
        if not self.is_available:
            return None

        plates = self.detect_plates(image, top_k=3)
        if not plates:
            return None

        best_result = None
        best_score = -1

        for conf, box in plates:
            try:
                crop = crop_region(image, box, margin_ratio=0.15)
            except Exception:
                continue

            # Try both raw and upscaled crops
            for crop_img in [crop, upscale_plate(crop, target_height=128)]:
                result = self.recognize_plate(crop_img)
                if result.text:
                    result.box = box
                    score = result.confidence + conf * 0.3
                    if score > best_score:
                        best_score = score
                        best_result = result

        return best_result
