"""Unit tests for the recognition pipeline orchestration.

Heavy ML services (YOLO/OCR) are swapped for tiny stubs so these tests
run instantly and deterministically, independent of whether ultralytics/
paddleocr are installed.
"""
from __future__ import annotations

import pytest

from app.config.settings import Settings
from app.exceptions import InvalidUploadError, RecognitionFailedError
from app.services.ocr_service import OCRResult
from app.services.plate_detection_service import PlateDetection
from app.services.recognition_service import RecognitionService
from app.services.vehicle_classification_service import ClassificationResult
from app.services.vehicle_detection_service import VehicleDetection
from app.utils.image_processing import BoundingBox


class StubVehicleDetector:
    def __init__(self, detection=None):
        self.detection = detection

    def detect_best(self, image):
        return self.detection

    def detect(self, image):
        return [self.detection] if self.detection else []


class StubPlateDetector:
    def __init__(self, detection=None):
        self.detection = detection

    def detect_plate(self, image):
        return self.detection

    def detect_plates(self, image, top_k=3):
        return [self.detection] if self.detection else []


class StubOCR:
    def __init__(self, result=None):
        self.result = result or OCRResult(text="", confidence=0.0, engine="stub")

    def read_plate(self, image):
        return self.result


class StubClassifier:
    def __init__(self, result):
        self.result = result

    def classify(self, crop, category, confidence):
        return self.result


def build_service(
    vehicle_detection=None,
    plate_detection=None,
    ocr_result=None,
    classification=None,
    **settings_overrides,
):
    settings = Settings(_env_file=None, **settings_overrides)
    classification = classification or ClassificationResult(
        vehicle_type="Car", wheel_key="car", confidence=0.9, refined=False
    )
    return RecognitionService(
        vehicle_detector=StubVehicleDetector(vehicle_detection),
        plate_detector=StubPlateDetector(plate_detection),
        ocr_service=StubOCR(ocr_result),
        classifier=StubClassifier(classification),
        settings=settings,
    )


def _box():
    return BoundingBox(10, 10, 100, 100)


def test_valid_car_image_full_success(sample_jpeg_bytes):
    service = build_service(
        vehicle_detection=VehicleDetection(category="car", confidence=0.97, box=_box()),
        plate_detection=PlateDetection(confidence=0.95, box=_box(), method="yolo"),
        ocr_result=OCRResult(text="TS09AB1234", confidence=0.91, engine="stub"),
        classification=ClassificationResult(vehicle_type="SUV", wheel_key="suv", confidence=0.97, refined=True),
    )

    result = service.recognize(sample_jpeg_bytes, "image/jpeg")

    assert result.vehicle_number == "TS09AB1234"
    assert result.wheel_category == 4
    assert result.vehicle_type == "SUV"
    assert result.confidence == pytest.approx(0.94, abs=0.01)
    assert result.details.vehicle_detection_confidence == 0.97
    assert result.details.plate_detection_confidence == 0.95
    assert result.details.ocr_confidence == 0.91
    assert result.warnings == []


def test_valid_bike_image(sample_jpeg_bytes):
    service = build_service(
        vehicle_detection=VehicleDetection(category="motorcycle", confidence=0.9, box=_box()),
        plate_detection=PlateDetection(confidence=0.8, box=_box(), method="yolo"),
        ocr_result=OCRResult(text="TS10XY9087", confidence=0.85, engine="stub"),
        classification=ClassificationResult(vehicle_type="Bike", wheel_key="bike", confidence=0.9, refined=False),
    )

    result = service.recognize(sample_jpeg_bytes, "image/jpeg")

    assert result.vehicle_number == "TS10XY9087"
    assert result.wheel_category == 2
    assert result.vehicle_type == "Bike"


def test_plate_detected_populates_plate_confidence(sample_jpeg_bytes):
    service = build_service(
        vehicle_detection=VehicleDetection(category="car", confidence=0.9, box=_box()),
        plate_detection=PlateDetection(confidence=0.88, box=_box(), method="yolo"),
        ocr_result=OCRResult(text="AP16CD5678", confidence=0.8, engine="stub"),
    )

    result = service.recognize(sample_jpeg_bytes, "image/jpeg")
    assert result.details.plate_detection_confidence == 0.88


def test_no_plate_detected_returns_null_vehicle_number_with_warning(sample_jpeg_bytes):
    service = build_service(
        vehicle_detection=VehicleDetection(category="car", confidence=0.91, box=_box()),
        plate_detection=None,
        classification=ClassificationResult(vehicle_type="SUV", wheel_key="suv", confidence=0.91, refined=True),
    )

    result = service.recognize(sample_jpeg_bytes, "image/jpeg")

    assert result.vehicle_number is None
    assert result.vehicle_type == "SUV"
    assert result.wheel_category == 4
    assert "Number plate could not be detected" in result.warnings
    assert result.confidence == pytest.approx(0.71, abs=0.01)


def test_ocr_failure_returns_null_vehicle_number_with_warning(sample_jpeg_bytes):
    service = build_service(
        vehicle_detection=VehicleDetection(category="car", confidence=0.9, box=_box()),
        plate_detection=PlateDetection(confidence=0.85, box=_box(), method="yolo"),
        ocr_result=OCRResult(text="", confidence=0.0, engine="stub"),
    )

    result = service.recognize(sample_jpeg_bytes, "image/jpeg")

    assert result.vehicle_number is None
    assert "Unable to read registration number from detected plate" in result.warnings


def test_unsupported_file_type_is_rejected(sample_jpeg_bytes):
    service = build_service(
        vehicle_detection=VehicleDetection(category="car", confidence=0.9, box=_box())
    )

    with pytest.raises(InvalidUploadError):
        service.recognize(sample_jpeg_bytes, "text/plain")


def test_oversized_image_is_rejected():
    service = build_service(vehicle_detection=VehicleDetection(category="car", confidence=0.9, box=_box()))
    oversized = b"0" * (11 * 1024 * 1024)

    with pytest.raises(InvalidUploadError):
        service.recognize(oversized, "image/jpeg")


def test_low_confidence_result_is_returned_with_warnings_not_hidden(sample_jpeg_bytes):
    service = build_service(
        vehicle_detection=VehicleDetection(category="car", confidence=0.6, box=_box()),
        plate_detection=PlateDetection(confidence=0.55, box=_box(), method="heuristic"),
        ocr_result=OCRResult(text="TS09AB1234", confidence=0.4, engine="stub"),
        OCR_CONFIDENCE_THRESHOLD=0.6,
    )

    result = service.recognize(sample_jpeg_bytes, "image/jpeg")

    assert result.vehicle_number == "TS09AB1234"
    assert "Low OCR confidence" in result.warnings
    assert "Manual verification recommended" in result.warnings


def test_nothing_detected_raises_recognition_failed(sample_jpeg_bytes):
    service = build_service(vehicle_detection=None, plate_detection=None)

    with pytest.raises(RecognitionFailedError):
        service.recognize(sample_jpeg_bytes, "image/jpeg")
