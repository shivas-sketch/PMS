"""Orchestrates the full in-memory vehicle-recognition pipeline.

Uploaded Image -> Validation -> Preprocessing -> YOLO Vehicle Detection ->
Vehicle Classification -> Number Plate Detection -> Plate Crop -> Image
Enhancement -> OCR -> Registration Normalization -> Wheel Category Mapping
-> Confidence Calculation -> JSON Response.

Nothing here ever writes the image to disk; every array is a local
variable that goes out of scope (and is explicitly ``del``eted) once the
response has been built.
"""
from __future__ import annotations

import logging
from typing import List, Optional

import cv2
import numpy as np

from app.config.settings import Settings
from app.exceptions import InvalidUploadError, RecognitionFailedError
from app.schemas.recognition import RecognitionDetails, RecognitionResponse
from app.services.fast_alpr_service import FastALPRService
from app.services.lpr_service import LPRService
from app.services.ocr_service import OCRResult, OCRService, _looks_like_plate
from app.services.plate_detection_service import NumberPlateDetectionService, PlateDetection
from app.services.vehicle_classification_service import VehicleClassificationService
from app.services.vehicle_detection_service import VehicleDetectionService
from app.utils.image_processing import (
    BoundingBox,
    InvalidImageError,
    bytes_to_image,
    correct_perspective,
    crop_region,
    deskew,
    discard,
    enhance_plate_image,
    remove_borders,
    upscale_plate,
    validate_upload,
)
from app.utils.vehicle_number import normalize_vehicle_number

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

MAX_FRAME_DIMENSION = 1600

# Flat confidence penalties applied when a downstream signal is missing.
# Keeping these as named constants (rather than re-deriving a formula per
# call) makes the "don't fake certainty" behaviour easy to audit/tune.
NO_PLATE_PENALTY = 0.20
NO_OCR_PENALTY = 0.10


class RecognitionService:
    def __init__(
        self,
        vehicle_detector: VehicleDetectionService,
        plate_detector: NumberPlateDetectionService,
        ocr_service: OCRService,
        classifier: VehicleClassificationService,
        settings: Settings,
        lpr_service: Optional[LPRService] = None,
        fast_alpr_service: Optional[FastALPRService] = None,
    ):
        self.vehicle_detector = vehicle_detector
        self.plate_detector = plate_detector
        self.ocr_service = ocr_service
        self.classifier = classifier
        self.settings = settings
        self.lpr_service = lpr_service
        self.fast_alpr_service = fast_alpr_service

    def recognize(self, image_bytes: bytes, content_type: Optional[str]) -> RecognitionResponse:
        try:
            validate_upload(content_type, len(image_bytes), self.settings)
            frame = bytes_to_image(image_bytes)
        except InvalidImageError as exc:
            raise InvalidUploadError(str(exc)) from exc
        finally:
            # image_bytes is never needed again past this point.
            del image_bytes

        vehicle_crop: Optional[np.ndarray] = None
        try:
            frame = _preprocess(frame)

            best_vehicle = self.vehicle_detector.detect_best(frame)
            vehicle_conf = best_vehicle.confidence if best_vehicle else None

            if best_vehicle is not None:
                logger.info(
                    "recognition_pipeline: vehicle detected category=%s confidence=%.3f box=%s",
                    best_vehicle.category, best_vehicle.confidence, best_vehicle.box,
                )
            else:
                all_detections = self.vehicle_detector.detect(frame)
                logger.warning(
                    "recognition_pipeline: no vehicle detected. total_detections=%d, "
                    "frame_shape=%s, non_vehicle_classes=%s",
                    len(all_detections), frame.shape,
                    [(d.category, round(d.confidence, 3)) for d in all_detections],
                )

            if best_vehicle is not None:
                try:
                    vehicle_crop = crop_region(frame, best_vehicle.box, margin_ratio=0.08)
                except InvalidImageError:
                    vehicle_crop = None

            classification = self.classifier.classify(
                vehicle_crop,
                best_vehicle.category if best_vehicle else None,
                vehicle_conf or 0.0,
            )
            wheel_category = self.settings.WHEEL_MAPPING.get(
                classification.wheel_key, self.settings.WHEEL_MAPPING.get("other", 4)
            )

            plate_source = vehicle_crop if vehicle_crop is not None else frame

            # --- Fast-ALPR path: pretrained ONNX plate detection + OCR ---
            if self.fast_alpr_service and self.fast_alpr_service.is_available:
                alpr_plates = self.fast_alpr_service.recognize(plate_source)
                if alpr_plates:
                    best_alpr = None
                    best_alpr_norm = None
                    best_alpr_score = -1
                    for ap in alpr_plates:
                        norm = normalize_vehicle_number(ap.text)
                        logger.info(
                            "recognition_pipeline: FastALPR text=%r conf=%.3f det_conf=%.3f normalized=%r is_valid=%s",
                            ap.text, ap.confidence, ap.det_confidence,
                            norm.normalized, norm.is_valid_format,
                        )
                        score = (1000 if norm.is_valid_format else 0) + ap.confidence * 100 + ap.det_confidence
                        if score > best_alpr_score:
                            best_alpr_score = score
                            best_alpr = ap
                            best_alpr_norm = norm

                    if best_alpr and best_alpr_norm and best_alpr_norm.is_valid_format:
                        logger.info("recognition_pipeline: using FastALPR result (score=%.1f)", best_alpr_score)
                        ocr_result = OCRResult(
                            text=best_alpr.text,
                            confidence=best_alpr.confidence,
                            engine="fast-alpr",
                        )
                        normalization = best_alpr_norm
                        plate_conf = best_alpr.det_confidence
                        warnings = []
                        if vehicle_conf is not None and vehicle_conf < self.settings.VEHICLE_CONFIDENCE_THRESHOLD:
                            warnings.append("Low vehicle detection confidence")
                        if plate_conf < self.settings.PLATE_CONFIDENCE_THRESHOLD:
                            warnings.append("Low plate detection confidence")
                        if ocr_result.confidence < self.settings.OCR_CONFIDENCE_THRESHOLD:
                            warnings.append("Low OCR confidence")
                            warnings.append("Manual verification recommended")
                        if not normalization.is_valid_format:
                            warnings.append("Registration number format could not be fully verified")

                        return RecognitionResponse(
                            vehicle_number=normalization.normalized or None,
                            wheel_category=wheel_category,
                            vehicle_type=classification.vehicle_type,
                            confidence=_combine_confidence(vehicle_conf, plate_conf, ocr_result.confidence),
                            details=RecognitionDetails(
                                vehicle_detection_confidence=vehicle_conf,
                                plate_detection_confidence=plate_conf,
                                ocr_confidence=ocr_result.confidence,
                            ),
                            warnings=warnings,
                        )
                    elif best_alpr:
                        logger.info("recognition_pipeline: FastALPR result not valid format, falling back to YOLO+OCR pipeline")
                    else:
                        logger.info("recognition_pipeline: FastALPR produced no valid result, falling back to YOLO+OCR pipeline")

            plate_detections = self.plate_detector.detect_plates(plate_source, top_k=3)

            if not plate_detections:
                # Fallback: the uploaded image may itself be a close-up of a plate.
                # Try OCR directly on the full frame with perspective correction.
                logger.warning("recognition_pipeline: no plate detected, trying full-image OCR fallback")
                plate_detections = self._try_full_image_ocr(frame)

            if not plate_detections:
                if best_vehicle is None:
                    raise RecognitionFailedError()

                warnings = ["Number plate could not be detected"]
                if vehicle_conf is not None and vehicle_conf < self.settings.VEHICLE_CONFIDENCE_THRESHOLD:
                    warnings.append("Low vehicle detection confidence")

                return RecognitionResponse(
                    vehicle_number=None,
                    wheel_category=wheel_category,
                    vehicle_type=classification.vehicle_type,
                    confidence=_combine_confidence(vehicle_conf, None, None),
                    details=RecognitionDetails(vehicle_detection_confidence=vehicle_conf),
                    warnings=warnings,
                )

            best_plate = plate_detections[0]

            # --- LPR-first path: use trained LPRNet if available ---
            if self.lpr_service and self.lpr_service.is_available:
                lpr_best = None
                lpr_best_norm = None
                lpr_best_score = -1
                for pd in plate_detections:
                    try:
                        plate_crop = crop_region(plate_source, pd.box, margin_ratio=0.15)
                    except InvalidImageError:
                        continue
                    # Try raw and upscaled crops
                    for crop_img in [plate_crop, upscale_plate(plate_crop, target_height=128)]:
                        lpr_result = self.lpr_service.recognize_plate(crop_img)
                        if lpr_result.text:
                            norm = normalize_vehicle_number(lpr_result.text)
                            logger.info(
                                "recognition_pipeline: LPR plate_idx=%d conf=%.3f text=%r normalized=%r is_valid=%s",
                                plate_detections.index(pd), lpr_result.confidence, lpr_result.text,
                                norm.normalized, norm.is_valid_format,
                            )
                            score = (1000 if norm.is_valid_format else 0) + lpr_result.confidence * 100 + pd.confidence
                            if score > lpr_best_score:
                                lpr_best_score = score
                                lpr_best = lpr_result
                                lpr_best_norm = norm
                                best_plate = pd

                if lpr_best and lpr_best_norm and lpr_best_norm.is_valid_format:
                    logger.info("recognition_pipeline: using LPRNet result (score=%.1f)", lpr_best_score)
                    ocr_result = lpr_best
                    normalization = lpr_best_norm
                    # Skip PaddleOCR — LPR gave a valid result
                    warnings = []
                    if vehicle_conf is not None and vehicle_conf < self.settings.VEHICLE_CONFIDENCE_THRESHOLD:
                        warnings.append("Low vehicle detection confidence")
                    if best_plate.confidence < self.settings.PLATE_CONFIDENCE_THRESHOLD:
                        warnings.append("Low plate detection confidence")
                    if ocr_result.confidence < self.settings.OCR_CONFIDENCE_THRESHOLD:
                        warnings.append("Low OCR confidence")
                        warnings.append("Manual verification recommended")
                    if not normalization.is_valid_format:
                        warnings.append("Registration number format could not be fully verified")

                    return RecognitionResponse(
                        vehicle_number=normalization.normalized or None,
                        wheel_category=wheel_category,
                        vehicle_type=classification.vehicle_type,
                        confidence=_combine_confidence(vehicle_conf, best_plate.confidence, ocr_result.confidence),
                        details=RecognitionDetails(
                            vehicle_detection_confidence=vehicle_conf,
                            plate_detection_confidence=best_plate.confidence,
                            ocr_confidence=ocr_result.confidence,
                        ),
                        warnings=warnings,
                    )
                elif lpr_best:
                    logger.info("recognition_pipeline: LPR result not valid format, falling back to PaddleOCR")
                else:
                    logger.info("recognition_pipeline: LPR produced no result, falling back to PaddleOCR")

            # --- Fallback: PaddleOCR multi-strategy path ---
            # Try OCR on each detected plate and pick the best result that
            # normalizes to a valid plate format.
            #
            # For each plate detection we try multiple preparation strategies:
            #   1. Raw color crop (PaddleOCR's own preprocessing may work best)
            #   2. Upscaled color crop (for small plates)
            #   3. Full enhanced pipeline (grayscale + contrast + denoise + sharpen)
            #   4. Perspective-corrected + enhanced
            best_ocr = None
            best_norm = None
            best_score = -1
            for pd in plate_detections:
                try:
                    plate_crop = crop_region(plate_source, pd.box, margin_ratio=0.15)
                except InvalidImageError:
                    continue

                # Strategy 1: raw color crop (no preprocessing)
                raw_ocr = self.ocr_service.read_plate(plate_crop)
                if raw_ocr.text:
                    norm = normalize_vehicle_number(raw_ocr.text)
                    logger.info(
                        "recognition_pipeline: plate_idx=%d strategy=raw conf=%.3f ocr_raw=%r normalized=%r is_valid=%s",
                        plate_detections.index(pd), pd.confidence, raw_ocr.text,
                        norm.normalized, norm.is_valid_format,
                    )
                    score = (1000 if norm.is_valid_format else 0) + raw_ocr.confidence * 100 + pd.confidence
                    if score > best_score:
                        best_score = score
                        best_ocr = raw_ocr
                        best_norm = norm
                        best_plate = pd

                # Strategy 2: upscaled color crop
                upscaled_crop = upscale_plate(plate_crop, target_height=128)
                upscaled_ocr = self.ocr_service.read_plate(upscaled_crop)
                if upscaled_ocr.text:
                    norm = normalize_vehicle_number(upscaled_ocr.text)
                    logger.info(
                        "recognition_pipeline: plate_idx=%d strategy=upscaled conf=%.3f ocr_raw=%r normalized=%r is_valid=%s",
                        plate_detections.index(pd), pd.confidence, upscaled_ocr.text,
                        norm.normalized, norm.is_valid_format,
                    )
                    score = (1000 if norm.is_valid_format else 0) + upscaled_ocr.confidence * 100 + pd.confidence
                    if score > best_score:
                        best_score = score
                        best_ocr = upscaled_ocr
                        best_norm = norm
                        best_plate = pd

                # Strategy 3: perspective-corrected + full enhanced pipeline
                corrected = correct_perspective(plate_crop)
                enhanced_plate = enhance_plate_image(corrected)
                enhanced_ocr = self.ocr_service.read_plate(enhanced_plate)
                if enhanced_ocr.text:
                    norm = normalize_vehicle_number(enhanced_ocr.text)
                    logger.info(
                        "recognition_pipeline: plate_idx=%d strategy=enhanced conf=%.3f ocr_raw=%r normalized=%r is_valid=%s ocr_conf=%.3f",
                        plate_detections.index(pd), pd.confidence, enhanced_ocr.text,
                        norm.normalized, norm.is_valid_format, enhanced_ocr.confidence,
                    )
                    score = (1000 if norm.is_valid_format else 0) + enhanced_ocr.confidence * 100 + pd.confidence
                    if score > best_score:
                        best_score = score
                        best_ocr = enhanced_ocr
                        best_norm = norm
                        best_plate = pd

            ocr_result = best_ocr
            normalization = best_norm

            if not ocr_result or not ocr_result.text:
                if best_vehicle is None:
                    raise RecognitionFailedError()

                warnings = ["Unable to read registration number from detected plate"]
                if best_plate.confidence < self.settings.PLATE_CONFIDENCE_THRESHOLD:
                    warnings.append("Low plate detection confidence")

                return RecognitionResponse(
                    vehicle_number=None,
                    wheel_category=wheel_category,
                    vehicle_type=classification.vehicle_type,
                    confidence=_combine_confidence(vehicle_conf, best_plate.confidence, None),
                    details=RecognitionDetails(
                        vehicle_detection_confidence=vehicle_conf,
                        plate_detection_confidence=best_plate.confidence,
                    ),
                    warnings=warnings,
                )

            if not normalization:
                normalization = normalize_vehicle_number(ocr_result.text)

            warnings = []
            if vehicle_conf is not None and vehicle_conf < self.settings.VEHICLE_CONFIDENCE_THRESHOLD:
                warnings.append("Low vehicle detection confidence")
            if best_plate.confidence < self.settings.PLATE_CONFIDENCE_THRESHOLD:
                warnings.append("Low plate detection confidence")
            if ocr_result.confidence < self.settings.OCR_CONFIDENCE_THRESHOLD:
                warnings.append("Low OCR confidence")
                warnings.append("Manual verification recommended")
            if not normalization.is_valid_format:
                warnings.append("Registration number format could not be fully verified")

            return RecognitionResponse(
                vehicle_number=normalization.normalized or None,
                wheel_category=wheel_category,
                vehicle_type=classification.vehicle_type,
                confidence=_combine_confidence(vehicle_conf, best_plate.confidence, ocr_result.confidence),
                details=RecognitionDetails(
                    vehicle_detection_confidence=vehicle_conf,
                    plate_detection_confidence=best_plate.confidence,
                    ocr_confidence=ocr_result.confidence,
                ),
                warnings=warnings,
            )
        finally:
            # Explicit, immediate release - never persisted, never cached.
            discard(frame, vehicle_crop)

    def _try_full_image_ocr(self, frame: np.ndarray) -> List[PlateDetection]:
        """If the uploaded image is a close-up plate, run OCR on the whole frame.

        Tries multiple strategies (raw, upscaled, enhanced) and returns a
        synthetic PlateDetection if any OCR produces a plate-like result.
        """
        h, w = frame.shape[:2]

        strategies = [
            ("raw", frame),
            ("upscaled", upscale_plate(frame, target_height=128)),
            ("enhanced", enhance_plate_image(correct_perspective(frame))),
        ]

        best_text = ""
        best_conf = 0.0
        best_norm = None

        for label, image in strategies:
            ocr_result = self.ocr_service.read_plate(image)
            if not ocr_result.text:
                continue
            norm = normalize_vehicle_number(ocr_result.text)
            logger.info(
                "recognition_pipeline: full_image_fallback strategy=%s ocr_raw=%r normalized=%r is_valid=%s ocr_conf=%.3f",
                label, ocr_result.text, norm.normalized, norm.is_valid_format, ocr_result.confidence,
            )
            if norm.is_valid_format or _looks_like_plate(ocr_result.text):
                score = (1000 if norm.is_valid_format else 0) + ocr_result.confidence * 100
                best_score = (1000 if best_norm and best_norm.is_valid_format else 0) + best_conf * 100
                if score > best_score:
                    best_text = ocr_result.text
                    best_conf = ocr_result.confidence
                    best_norm = norm

        if best_text:
            return [PlateDetection(confidence=1.0, box=BoundingBox(0, 0, w, h), method="full_image_ocr")]
        return []

def _preprocess(frame: np.ndarray) -> np.ndarray:
    height, width = frame.shape[:2]
    longest = max(height, width)
    if longest <= MAX_FRAME_DIMENSION:
        return frame
    scale = MAX_FRAME_DIMENSION / float(longest)
    return cv2.resize(frame, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)


def _combine_confidence(
    vehicle_conf: Optional[float], plate_conf: Optional[float], ocr_conf: Optional[float]
) -> float:
    """Average the available sub-confidences, penalizing missing signals.

    - All three present: plain average.
    - Plate/OCR missing: average what's available, then subtract a flat
      penalty, so an incomplete read is never reported as confidently as a
      complete one.
    """
    if plate_conf is None:
        base = vehicle_conf if vehicle_conf is not None else 0.0
        return round(max(0.0, base - NO_PLATE_PENALTY), 2)

    if ocr_conf is None:
        components = [c for c in (vehicle_conf, plate_conf) if c is not None]
        base = sum(components) / len(components) if components else 0.0
        return round(max(0.0, base - NO_OCR_PENALTY), 2)

    components = [c for c in (vehicle_conf, plate_conf, ocr_conf) if c is not None]
    if not components:
        return 0.0
    return round(sum(components) / len(components), 2)
