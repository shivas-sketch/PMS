"""FastAPI application entrypoint.

Startup loads every heavy model (YOLO vehicle detector, YOLO/heuristic
plate detector, OCR engine) exactly once and stores the instances on
``app.state`` so every request reuses them - see ``lifespan`` below.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import parking, recognition
from app.config.firebase import get_firestore_client
from app.config.settings import get_settings
from app.exceptions import AppError
from app.repositories.parking_repository import ParkingRepository
from app.repositories.timeline_repository import TimelineRepository
from app.services.fast_alpr_service import FastALPRService
from app.services.lpr_service import LPRService
from app.services.ocr_service import OCRService
from app.services.parking_service import ParkingService
from app.services.plate_detection_service import NumberPlateDetectionService
from app.services.recognition_service import RecognitionService
from app.services.alert_service import AlertService
from app.services.timeline_service import TimelineService
from app.services.vehicle_classification_service import VehicleClassificationService
from app.services.vehicle_detection_service import VehicleDetectionService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings

    logger.info("Loading vehicle detection model...")
    vehicle_detector = VehicleDetectionService(model_path=settings.VEHICLE_MODEL_PATH)
    vehicle_detector.load()

    logger.info("Loading plate detection model...")
    plate_detector = NumberPlateDetectionService(model_path=settings.LICENSE_PLATE_MODEL_PATH)
    plate_detector.load()

    logger.info("Loading OCR engine...")
    ocr_service = OCRService(preferred_engine=settings.OCR_ENGINE, languages=settings.OCR_LANGUAGES)
    ocr_service.load()

    classifier = VehicleClassificationService(classifier_model_path=settings.VEHICLE_CLASSIFIER_MODEL_PATH)
    classifier.load()

    # Load end-to-end LPR model if configured (used as primary plate recognition)
    lpr_service = None
    if settings.LPRNET_MODEL_PATH:
        logger.info("Loading LPRNet recognition model...")
        lpr_service = LPRService(
            detection_model_path=settings.LICENSE_PLATE_MODEL_PATH,
            recognition_model_path=settings.LPRNET_MODEL_PATH,
        )
        lpr_service.load()
        if lpr_service.is_available:
            logger.info("LPRNet ready — will be used as primary plate recognition engine.")
        else:
            logger.warning("LPRNet model not available, falling back to PaddleOCR pipeline.")
            lpr_service = None
    # Load fast-alpr (pretrained ONNX plate recognition) if enabled
    fast_alpr_service = None
    if settings.USE_FAST_ALPR:
        logger.info("Loading Fast-ALPR plate recognition models...")
        fast_alpr_service = FastALPRService()
        fast_alpr_service.load()
        if fast_alpr_service.is_available:
            logger.info("Fast-ALPR ready — will be used as primary plate recognition engine.")
        else:
            logger.warning("Fast-ALPR not available, falling back to PaddleOCR pipeline.")
            fast_alpr_service = None
    app.state.fast_alpr_service = fast_alpr_service

    app.state.lpr_service = lpr_service

    app.state.recognition_service = RecognitionService(
        vehicle_detector=vehicle_detector,
        plate_detector=plate_detector,
        ocr_service=ocr_service,
        classifier=classifier,
        settings=settings,
        lpr_service=lpr_service,
        fast_alpr_service=fast_alpr_service,
    )

    try:
        db = get_firestore_client()
        repository = ParkingRepository(db)
        repository.ensure_config(total_capacity=settings.DEFAULT_TOTAL_CAPACITY)
        timeline_repository = TimelineRepository(db)
        alert_service = AlertService(repository)
        app.state.parking_repository = repository
        app.state.parking_service = ParkingService(repository, alert_service=alert_service)
        app.state.alert_service = alert_service
        app.state.timeline_repository = timeline_repository
        app.state.timeline_service = TimelineService(repository, timeline_repository)
        logger.info("Firestore connected and parking_config/main ensured.")
    except Exception as exc:  # pragma: no cover
        logger.error("Firestore initialization failed: %s. Parking endpoints will error until fixed.", exc)
        app.state.parking_repository = None
        app.state.parking_service = None
        app.state.alert_service = None
        app.state.timeline_repository = None
        app.state.timeline_service = None

    logger.info("Application ready.")
    yield
    logger.info("Application shutting down.")


app = FastAPI(
    title="Hospital Valet Parking Management API",
    description="Vehicle recognition (YOLO + OCR, in-memory only) and Firestore-backed parking capacity management.",
    version="1.0.0",
    lifespan=lifespan,
)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.error_code, "message": exc.message})


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error while processing %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "INTERNAL_SERVER_ERROR", "message": "An unexpected error occurred"},
    )


app.include_router(recognition.router, prefix="/api")
app.include_router(parking.router, prefix="/api")


@app.get("/", tags=["health"])
def root():
    return {"service": "hospital-valet-parking-api", "status": "ok"}


@app.get("/health", tags=["health"])
def health():
    return {"status": "healthy"}
