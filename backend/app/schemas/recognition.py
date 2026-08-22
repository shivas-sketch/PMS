"""Request/response contracts for POST /api/vehicle-recognition."""
from __future__ import annotations

from typing import List, Optional

from pydantic import Field

from app.schemas.common import CamelModel


class RecognitionDetails(CamelModel):
    vehicle_detection_confidence: Optional[float] = None
    plate_detection_confidence: Optional[float] = None
    ocr_confidence: Optional[float] = None


class RecognitionResponse(CamelModel):
    vehicle_number: Optional[str] = None
    wheel_category: int
    vehicle_type: str
    confidence: float
    details: RecognitionDetails = Field(default_factory=RecognitionDetails)
    warnings: List[str] = Field(default_factory=list)


class ErrorResponse(CamelModel):
    error: str
    message: str
