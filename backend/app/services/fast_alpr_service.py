"""Fast-ALPR plate recognition service.

Wraps the ``fast-alpr`` library which uses a pretrained ONNX YOLOv9 plate
detector and a compact transformer (CCT) OCR model for end-to-end plate
recognition — no custom training required.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class FastALPRPlate:
    text: str
    confidence: float
    det_confidence: float
    x1: int
    y1: int
    x2: int
    y2: int


class FastALPRService:
    def __init__(self) -> None:
        self._alpr = None
        self._load_error: Optional[str] = None
        self._load_attempted = False

    def load(self) -> None:
        if self._load_attempted:
            return
        self._load_attempted = True
        try:
            from fast_alpr import ALPR

            self._alpr = ALPR(
                detector_model="yolo-v9-t-384-license-plate-end2end",
                ocr_model="cct-xs-v2-global-model",
            )
            logger.info("FastALPRService: models loaded (YOLOv9 detector + CCT OCR)")
        except Exception as exc:
            self._load_error = str(exc)
            logger.warning("FastALPRService: failed to load — %s", exc)

    @property
    def is_available(self) -> bool:
        return self._alpr is not None

    def recognize(self, frame: np.ndarray) -> List[FastALPRPlate]:
        """Run plate detection + OCR on a BGR image.

        Args:
            frame: BGR numpy ndarray (vehicle crop or full frame).

        Returns:
            List of detected plates with text, confidence, and bounding box.
        """
        if self._alpr is None:
            return []

        try:
            results = self._alpr.predict(frame)
        except Exception as exc:
            logger.warning("FastALPRService: predict failed — %s", exc)
            return []

        plates: List[FastALPRPlate] = []
        for r in results:
            if r.ocr is None or not r.ocr.text:
                continue
            conf = r.ocr.confidence
            if isinstance(conf, list):
                conf = sum(conf) / len(conf) if conf else 0.0
            bb = r.detection.bounding_box
            plates.append(FastALPRPlate(
                text=r.ocr.text,
                confidence=float(conf),
                det_confidence=r.detection.confidence,
                x1=int(bb.x1), y1=int(bb.y1),
                x2=int(bb.x2), y2=int(bb.y2),
            ))
            logger.info(
                "FastALPR: text=%r conf=%.3f det_conf=%.3f box=(%d,%d,%d,%d)",
                r.ocr.text, conf, r.detection.confidence,
                bb.x1, bb.y1, bb.x2, bb.y2,
            )
        return plates
