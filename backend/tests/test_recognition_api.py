from __future__ import annotations

from fastapi.testclient import TestClient

from app.dependencies import get_recognition_service
from app.main import app
from app.services.ocr_service import OCRResult
from app.services.plate_detection_service import PlateDetection
from app.services.vehicle_classification_service import ClassificationResult
from app.services.vehicle_detection_service import VehicleDetection
from app.utils.image_processing import BoundingBox
from tests.test_recognition_service import build_service


def test_recognition_endpoint_happy_path(sample_jpeg_bytes):
    box = BoundingBox(0, 0, 50, 50)
    service = build_service(
        vehicle_detection=VehicleDetection(category="car", confidence=0.95, box=box),
        plate_detection=PlateDetection(confidence=0.9, box=box, method="yolo"),
        ocr_result=OCRResult(text="TS09AB1234", confidence=0.9, engine="stub"),
        classification=ClassificationResult(vehicle_type="SUV", wheel_key="suv", confidence=0.95, refined=True),
    )
    app.dependency_overrides[get_recognition_service] = lambda: service

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/vehicle-recognition",
                files={"image": ("car.jpg", sample_jpeg_bytes, "image/jpeg")},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["vehicleNumber"] == "TS09AB1234"
        assert body["wheelCategory"] == 4
        assert body["vehicleType"] == "SUV"
        assert "image" not in body
        assert "imageUrl" not in body
        assert "base64" not in str(body).lower()
    finally:
        app.dependency_overrides.pop(get_recognition_service, None)


def test_recognition_endpoint_rejects_unsupported_file_type(sample_jpeg_bytes):
    service = build_service()
    app.dependency_overrides[get_recognition_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/vehicle-recognition",
                files={"image": ("notes.txt", b"hello world", "text/plain")},
            )
        assert response.status_code == 400
        assert response.json()["error"] == "INVALID_IMAGE"
    finally:
        app.dependency_overrides.pop(get_recognition_service, None)


def test_recognition_endpoint_rejects_oversized_image():
    service = build_service()
    app.dependency_overrides[get_recognition_service] = lambda: service
    try:
        oversized = b"0" * (11 * 1024 * 1024)
        with TestClient(app) as client:
            response = client.post(
                "/api/vehicle-recognition",
                files={"image": ("car.jpg", oversized, "image/jpeg")},
            )
        assert response.status_code == 400
        assert response.json()["error"] == "INVALID_IMAGE"
    finally:
        app.dependency_overrides.pop(get_recognition_service, None)


def test_recognition_endpoint_returns_422_when_nothing_detected(sample_jpeg_bytes):
    service = build_service(vehicle_detection=None, plate_detection=None)
    app.dependency_overrides[get_recognition_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/vehicle-recognition",
                files={"image": ("blank.jpg", sample_jpeg_bytes, "image/jpeg")},
            )
        assert response.status_code == 422
        body = response.json()
        assert body["error"] == "VEHICLE_RECOGNITION_FAILED"
    finally:
        app.dependency_overrides.pop(get_recognition_service, None)
