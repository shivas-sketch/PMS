"""POST /api/vehicle-recognition

Accepts a single multipart image, processes it entirely in memory, and
returns structured vehicle/plate/confidence data. The image is never
written to disk, Firestore, or any other store, and is never echoed back
in the response (no raw bytes, no Base64, no URL).
"""
from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter, Depends, File, UploadFile

from app.dependencies import get_recognition_service
from app.schemas.recognition import RecognitionResponse
from app.services.recognition_service import RecognitionService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["recognition"])


@router.post("/vehicle-recognition", response_model=RecognitionResponse)
async def recognize_vehicle(
    image: UploadFile = File(...),
    recognition_service: RecognitionService = Depends(get_recognition_service),
) -> RecognitionResponse:
    request_id = uuid.uuid4().hex[:12]
    started_at = time.perf_counter()

    image_bytes = await image.read()
    content_type = image.content_type

    try:
        result = recognition_service.recognize(image_bytes, content_type)
        duration_ms = round((time.perf_counter() - started_at) * 1000, 1)
        logger.info(
            "recognition request_id=%s duration_ms=%s vehicle_number=%s confidence=%s status=success",
            request_id, duration_ms, result.vehicle_number, result.confidence,
        )
        return result
    except Exception:
        duration_ms = round((time.perf_counter() - started_at) * 1000, 1)
        logger.info(
            "recognition request_id=%s duration_ms=%s status=failed",
            request_id, duration_ms,
        )
        raise
    finally:
        del image_bytes
