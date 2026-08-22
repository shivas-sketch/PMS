import os

# Point firebase-admin/google-cloud-firestore at a (deliberately unreachable)
# local emulator address *before* app.main is ever imported, so accidental
# Firestore initialization during tests fails fast instead of trying real
# GCP Application Default Credentials / network calls.
os.environ.setdefault("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8199")
os.environ.setdefault("FIREBASE_PROJECT_ID", "test-project")

import cv2
import numpy as np
import pytest


def _encode(image: np.ndarray, ext: str) -> bytes:
    ok, buffer = cv2.imencode(ext, image)
    assert ok
    return buffer.tobytes()


@pytest.fixture
def blank_image() -> np.ndarray:
    return np.full((240, 480, 3), 200, dtype=np.uint8)


@pytest.fixture
def sample_jpeg_bytes(blank_image) -> bytes:
    return _encode(blank_image, ".jpg")


@pytest.fixture
def sample_png_bytes(blank_image) -> bytes:
    return _encode(blank_image, ".png")
