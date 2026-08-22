"""Central application configuration.

All tunables required by the spec (model paths, thresholds, wheel-category
mapping, Firebase project, upload limits) are exposed here as environment
variables so behaviour can change without code edits.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Dict

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    APP_NAME: str = "Hospital Valet Parking Management API"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: str = "*"

    # --- Firebase / Firestore ---
    FIREBASE_PROJECT_ID: str = "smart-hospital-parking"
    FIREBASE_CREDENTIALS_PATH: str = ""
    FIRESTORE_EMULATOR_HOST: str = ""

    # --- Model paths (kept configurable / replaceable) ---
    VEHICLE_MODEL_PATH: str = "yolo11n.pt"
    LICENSE_PLATE_MODEL_PATH: str = ""
    VEHICLE_CLASSIFIER_MODEL_PATH: str = ""
    LPRNET_MODEL_PATH: str = ""  # Trained LPRNet for end-to-end plate recognition
    USE_FAST_ALPR: bool = True  # Use fast-alpr (pretrained ONNX) as primary plate recognition

    # --- OCR ---
    OCR_ENGINE: str = "paddleocr"  # paddleocr | easyocr
    OCR_LANGUAGES: str = "en"

    # --- Confidence thresholds ---
    VEHICLE_CONFIDENCE_THRESHOLD: float = 0.50
    PLATE_CONFIDENCE_THRESHOLD: float = 0.50
    OCR_CONFIDENCE_THRESHOLD: float = 0.60

    # --- Upload limits ---
    MAX_UPLOAD_SIZE_MB: float = 10.0
    ALLOWED_IMAGE_CONTENT_TYPES: str = "image/jpeg,image/png,image/webp"

    # --- Parking ---
    DEFAULT_TOTAL_CAPACITY: int = 100

    # --- Wheel category mapping (vehicle_type key -> wheel count) ---
    WHEEL_MAPPING: Dict[str, int] = {
        "bike": 2,
        "motorcycle": 2,
        "scooter": 2,
        "auto_rickshaw": 3,
        "hatchback": 4,
        "sedan": 4,
        "suv": 4,
        "car": 4,
        "van": 4,
        "pickup": 4,
        "truck": 6,
        "bus": 6,
        "other": 4,
    }

    @property
    def allowed_content_types(self) -> set[str]:
        return {c.strip() for c in self.ALLOWED_IMAGE_CONTENT_TYPES.split(",") if c.strip()}

    @property
    def max_upload_size_bytes(self) -> int:
        return int(self.MAX_UPLOAD_SIZE_MB * 1024 * 1024)

    @property
    def cors_origins_list(self) -> list[str]:
        if self.CORS_ORIGINS == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
