"""FastAPI dependency providers.

All heavy singletons (YOLO models, OCR engine, Firestore client) are
created exactly once in ``app.main``'s lifespan handler and stashed on
``app.state``; these functions just hand them to route handlers.
"""
from __future__ import annotations

from fastapi import Request

from app.config.settings import Settings
from app.repositories.parking_repository import ParkingRepository
from app.repositories.timeline_repository import TimelineRepository
from app.services.parking_service import ParkingService
from app.services.recognition_service import RecognitionService
from app.services.timeline_service import TimelineService


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_recognition_service(request: Request) -> RecognitionService:
    return request.app.state.recognition_service


def get_parking_repository(request: Request) -> ParkingRepository:
    return request.app.state.parking_repository


def get_parking_service(request: Request) -> ParkingService:
    return request.app.state.parking_service


def get_timeline_repository(request: Request) -> TimelineRepository:
    return request.app.state.timeline_repository


def get_timeline_service(request: Request) -> TimelineService:
    return request.app.state.timeline_service
