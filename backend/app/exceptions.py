"""Domain exceptions that map 1:1 onto the API error contract.

Each exception carries the HTTP status code and the exact
``{"error": ..., "message": ...}`` body the spec requires. A single
FastAPI exception handler (registered in ``app.main``) turns any of these
into the right response, so route handlers just raise and move on.
"""
from __future__ import annotations


class AppError(Exception):
    status_code: int = 400
    error_code: str = "APP_ERROR"

    def __init__(self, message: str, status_code: int | None = None, error_code: str | None = None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        if error_code is not None:
            self.error_code = error_code


class InvalidUploadError(AppError):
    status_code = 400
    error_code = "INVALID_IMAGE"


class RecognitionFailedError(AppError):
    status_code = 422
    error_code = "VEHICLE_RECOGNITION_FAILED"

    def __init__(self, message: str = "Unable to reliably identify the vehicle"):
        super().__init__(message)


class VehicleAlreadyActiveError(AppError):
    status_code = 409
    error_code = "VEHICLE_ALREADY_ACTIVE"

    def __init__(self, message: str = "Vehicle is already inside the parking area"):
        super().__init__(message)


class ParkingFullError(AppError):
    status_code = 409
    error_code = "PARKING_FULL"

    def __init__(self, message: str = "Parking is full"):
        super().__init__(message)


class VehicleAlreadyExitedError(AppError):
    status_code = 409
    error_code = "VEHICLE_ALREADY_EXITED"

    def __init__(self, message: str = "Vehicle has already exited"):
        super().__init__(message)


class VehicleNotFoundError(AppError):
    status_code = 404
    error_code = "VEHICLE_NOT_FOUND"

    def __init__(self, message: str = "Vehicle not found"):
        super().__init__(message)


class ParkingConfigMissingError(AppError):
    status_code = 500
    error_code = "PARKING_CONFIG_MISSING"

    def __init__(self, message: str = "Parking configuration has not been initialized"):
        super().__init__(message)


class ParkingAreaNotFoundError(AppError):
    status_code = 404
    error_code = "PARKING_AREA_NOT_FOUND"

    def __init__(self, message: str = "Parking area not found"):
        super().__init__(message)


class ParkingSlotNotFoundError(AppError):
    status_code = 404
    error_code = "PARKING_SLOT_NOT_FOUND"

    def __init__(self, message: str = "Parking slot not found"):
        super().__init__(message)


class SlotAlreadyOccupiedError(AppError):
    status_code = 409
    error_code = "SLOT_ALREADY_OCCUPIED"

    def __init__(self, message: str = "Parking slot is already occupied"):
        super().__init__(message)


class AreaHasActiveSlotsError(AppError):
    status_code = 409
    error_code = "AREA_HAS_ACTIVE_SLOTS"

    def __init__(self, message: str = "Cannot delete area with occupied slots"):
        super().__init__(message)


class DuplicateSlotError(AppError):
    status_code = 409
    error_code = "DUPLICATE_SLOT"

    def __init__(self, message: str = "A slot with this number already exists in this area"):
        super().__init__(message)


class ParkingSessionNotFoundError(AppError):
    status_code = 404
    error_code = "PARKING_SESSION_NOT_FOUND"

    def __init__(self, message: str = "Parking session not found"):
        super().__init__(message)


class ParkingSlotRequiredError(AppError):
    status_code = 422
    error_code = "PARKING_SLOT_REQUIRED"

    def __init__(self, message: str = "A parking slot is required before marking the vehicle as parked"):
        super().__init__(message)


class CorridorFullError(AppError):
    status_code = 409
    error_code = "CORRIDOR_FULL"

    def __init__(self, message: str = "Corridor parking is full in this area"):
        super().__init__(message)


class InvalidCorridorCapacityError(AppError):
    status_code = 422
    error_code = "INVALID_CORRIDOR_CAPACITY"

    def __init__(self, message: str = "Corridor capacity cannot be less than the number of currently occupied corridor slots"):
        super().__init__(message)
