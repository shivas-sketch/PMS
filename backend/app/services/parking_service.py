"""Business layer for parking capacity/vehicle/session operations.

Thin on purpose: validation of the transactional invariants (capacity,
duplicate-active, double-exit) lives in
``app.repositories.parking_repository`` where the Firestore transaction
is; this layer just maps repository dicts to API schemas and normalizes
lookup keys.
"""
from __future__ import annotations

from typing import List, Optional

from app.exceptions import ParkingAreaNotFoundError, VehicleNotFoundError
from app.repositories.parking_repository import ParkingRepository
from app.schemas.parking import (
    AddVehicleRequest,
    BulkCreateSlotsResponse,
    CapacityResponse,
    CreateAreaRequest,
    CreateSlotRequest,
    ParkingAreaListResponse,
    ParkingAreaResponse,
    ParkingSessionResponse,
    ParkingSlotListResponse,
    ParkingSlotResponse,
    ReassignSlotRequest,
    UpdateSessionRequest,
    UpdateSlotRequest,
    VehicleListResponse,
)
from app.services.alert_service import AlertService
from app.utils.vehicle_number import clean_vehicle_number


class ParkingService:
    def __init__(self, repository: ParkingRepository, alert_service: AlertService | None = None):
        self.repository = repository
        self.alert_service = alert_service

    def get_capacity(self) -> CapacityResponse:
        config = self.repository.get_capacity()
        return CapacityResponse(
            total_capacity=config.get("totalCapacity", 0),
            available_slots=config.get("availableSlots", 0),
            occupied_slots=config.get("occupiedSlots", 0),
        )

    def add_vehicle(self, request: AddVehicleRequest) -> ParkingSessionResponse:
        session = self.repository.add_vehicle(
            vehicle_number=request.vehicle_number,
            wheel_category=request.wheel_category,
            vehicle_type=request.vehicle_type,
            hospital_side=request.hospital_side,
            area_id=request.area_id,
            slot_id=request.slot_id,
        )
        if self.alert_service:
            try:
                self.alert_service.check_capacity()
            except Exception:
                pass
        return ParkingSessionResponse.model_validate(session)

    def exit_vehicle(self, vehicle_number: str) -> ParkingSessionResponse:
        cleaned = clean_vehicle_number(vehicle_number)
        session = self.repository.exit_vehicle(cleaned)
        if self.alert_service:
            try:
                self.alert_service.check_capacity()
            except Exception:
                pass
        return ParkingSessionResponse.model_validate(session)

    def reassign_slot(self, vehicle_number: str, slot_id: str) -> ParkingSessionResponse:
        cleaned = clean_vehicle_number(vehicle_number)
        session = self.repository.reassign_slot(cleaned, slot_id)
        return ParkingSessionResponse.model_validate(session)

    def list_vehicles(self, status: Optional[str] = "ACTIVE") -> VehicleListResponse:
        normalized_status = status.upper() if status and status.upper() != "ALL" else None
        sessions = self.repository.list_sessions(status=normalized_status)
        items = [ParkingSessionResponse.model_validate(s) for s in sessions]
        return VehicleListResponse(vehicles=items, count=len(items))

    def get_vehicle(self, vehicle_number: str) -> ParkingSessionResponse:
        cleaned = clean_vehicle_number(vehicle_number)
        session = self.repository.get_current_session_for_vehicle(cleaned)
        if session is None:
            raise VehicleNotFoundError(f"No parking record found for vehicle '{cleaned}'")
        return ParkingSessionResponse.model_validate(session)

    # --- parking areas --------------------------------------------------
    def create_area(self, request: CreateAreaRequest) -> ParkingAreaResponse:
        area = self.repository.create_area(
            name=request.name,
            area_type=request.area_type,
            description=request.description,
        )
        return ParkingAreaResponse.model_validate(area)

    def list_areas(self) -> ParkingAreaListResponse:
        areas = self.repository.list_areas()
        items = [ParkingAreaResponse.model_validate(a) for a in areas]
        return ParkingAreaListResponse(areas=items, count=len(items))

    def delete_area(self, area_id: str) -> None:
        self.repository.delete_area(area_id)

    # --- parking slots --------------------------------------------------
    def create_slot(self, area_id: str, request: CreateSlotRequest) -> ParkingSlotResponse:
        slot = self.repository.create_slot(area_id, request.slot_number)
        return ParkingSlotResponse.model_validate(slot)

    def list_slots(self, area_id: str) -> ParkingSlotListResponse:
        area = self.repository.get_area(area_id)
        if area is None:
            raise ParkingAreaNotFoundError()
        slots = self.repository.list_slots(area_id)
        items = [ParkingSlotResponse.model_validate(s) for s in slots]
        return ParkingSlotListResponse(slots=items, count=len(items))

    def delete_slot(self, slot_id: str) -> None:
        self.repository.delete_slot(slot_id)

    def create_slots_bulk(
        self,
        area_id: str,
        count: int,
        prefix: Optional[str] = None,
        start_index: int = 1,
    ) -> BulkCreateSlotsResponse:
        slots = self.repository.create_slots_bulk(
            area_id=area_id,
            count=count,
            prefix=prefix,
            start_index=start_index,
        )
        items = [ParkingSlotResponse.model_validate(s) for s in slots]
        return BulkCreateSlotsResponse(created=len(items), slots=items)

    def update_session(self, session_id: str, request: UpdateSessionRequest) -> ParkingSessionResponse:
        session = self.repository.update_session(
            session_id=session_id,
            vehicle_type=request.vehicle_type,
            wheel_category=request.wheel_category,
            hospital_side=request.hospital_side,
        )
        return ParkingSessionResponse.model_validate(session)

    def update_slot(self, slot_id: str, request: UpdateSlotRequest) -> ParkingSlotResponse:
        slot = self.repository.update_slot(
            slot_id=slot_id,
            slot_number=request.slot_number,
            status=request.status,
        )
        return ParkingSlotResponse.model_validate(slot)
