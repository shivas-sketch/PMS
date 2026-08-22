"""Parking registration & monitoring API.

Deliberately separate from recognition: these endpoints only ever accept
structured JSON (vehicle number / wheel category / vehicle type) and never
an image. Capacity only changes here, via Firestore transactions in
``ParkingRepository``.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, status

from app.dependencies import get_parking_service, get_timeline_service
from app.enums import ParkingTimelineStage
from app.schemas.parking import (
    AddVehicleRequest,
    BulkCreateSlotsRequest,
    BulkCreateSlotsResponse,
    CapacityResponse,
    CreateAreaRequest,
    CreateSlotRequest,
    CreateTimelineEventRequest,
    ParkingAreaListResponse,
    ParkingAreaResponse,
    ParkingSessionResponse,
    ParkingSlotListResponse,
    ParkingSlotResponse,
    ParkingTimelineEventResponse,
    ParkingTimelineListResponse,
    ReassignSlotRequest,
    TimelineActionRequest,
    UpdateSessionRequest,
    UpdateSlotRequest,
    VehicleListResponse,
)
from app.services.parking_service import ParkingService
from app.services.timeline_service import TimelineService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/parking", tags=["parking"])


# --- vehicle endpoints --------------------------------------------------

@router.post("/vehicles", response_model=ParkingSessionResponse, status_code=status.HTTP_201_CREATED)
def add_vehicle(
    payload: AddVehicleRequest,
    parking_service: ParkingService = Depends(get_parking_service),
    timeline_service: TimelineService = Depends(get_timeline_service),
) -> ParkingSessionResponse:
    session = parking_service.add_vehicle(payload)
    logger.info(
        "parking_add vehicle_number=%s wheel_category=%s vehicle_type=%s session_id=%s",
        session.vehicle_number, session.wheel_category, session.vehicle_type, session.session_id,
    )
    # First timeline entry always records the entry; if a slot was assigned
    # immediately the vehicle is already physically parked, so record that
    # too (see spec 15.4 - "if a slot is immediately allocated...").
    timeline_service.add_event(session.session_id, ParkingTimelineStage.ASSIGNED_FOR_PARKING)
    if session.slot_id:
        timeline_service.add_event(session.session_id, ParkingTimelineStage.PARKED)
        session = parking_service.get_vehicle(session.vehicle_number)
    return session


@router.get("/vehicles", response_model=VehicleListResponse)
def list_vehicles(
    status_filter: Optional[str] = Query("ACTIVE", alias="status"),
    parking_service: ParkingService = Depends(get_parking_service),
) -> VehicleListResponse:
    return parking_service.list_vehicles(status=status_filter)


@router.get("/vehicles/{vehicle_number}", response_model=ParkingSessionResponse)
def get_vehicle(
    vehicle_number: str,
    parking_service: ParkingService = Depends(get_parking_service),
) -> ParkingSessionResponse:
    return parking_service.get_vehicle(vehicle_number)


@router.post("/vehicles/{vehicle_number}/exit", response_model=ParkingSessionResponse)
def exit_vehicle(
    vehicle_number: str,
    parking_service: ParkingService = Depends(get_parking_service),
) -> ParkingSessionResponse:
    session = parking_service.exit_vehicle(vehicle_number)
    logger.info("parking_exit vehicle_number=%s session_id=%s", session.vehicle_number, session.session_id)
    return session


@router.patch("/vehicles/{vehicle_number}/slot", response_model=ParkingSessionResponse)
def reassign_slot(
    vehicle_number: str,
    payload: ReassignSlotRequest,
    parking_service: ParkingService = Depends(get_parking_service),
) -> ParkingSessionResponse:
    session = parking_service.reassign_slot(vehicle_number, payload.slot_id)
    logger.info(
        "parking_reassign vehicle_number=%s new_slot_id=%s session_id=%s",
        session.vehicle_number, payload.slot_id, session.session_id,
    )
    return session


@router.patch("/sessions/{session_id}", response_model=ParkingSessionResponse)
def update_session(
    session_id: str,
    payload: UpdateSessionRequest,
    parking_service: ParkingService = Depends(get_parking_service),
) -> ParkingSessionResponse:
    session = parking_service.update_session(session_id, payload)
    logger.info("parking_update session_id=%s", session.session_id)
    return session


@router.get("/capacity", response_model=CapacityResponse)
def get_capacity(
    parking_service: ParkingService = Depends(get_parking_service),
) -> CapacityResponse:
    return parking_service.get_capacity()


# --- parking area endpoints ---------------------------------------------

@router.post("/areas", response_model=ParkingAreaResponse, status_code=status.HTTP_201_CREATED)
def create_area(
    payload: CreateAreaRequest,
    parking_service: ParkingService = Depends(get_parking_service),
) -> ParkingAreaResponse:
    return parking_service.create_area(payload)


@router.get("/areas", response_model=ParkingAreaListResponse)
def list_areas(
    parking_service: ParkingService = Depends(get_parking_service),
) -> ParkingAreaListResponse:
    return parking_service.list_areas()


@router.delete("/areas/{area_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_area(
    area_id: str,
    parking_service: ParkingService = Depends(get_parking_service),
):
    parking_service.delete_area(area_id)


# --- parking slot endpoints ---------------------------------------------

@router.post("/areas/{area_id}/slots", response_model=ParkingSlotResponse, status_code=status.HTTP_201_CREATED)
def create_slot(
    area_id: str,
    payload: CreateSlotRequest,
    parking_service: ParkingService = Depends(get_parking_service),
) -> ParkingSlotResponse:
    return parking_service.create_slot(area_id, payload)


@router.post("/areas/{area_id}/slots/bulk", response_model=BulkCreateSlotsResponse, status_code=status.HTTP_201_CREATED)
def create_slots_bulk(
    area_id: str,
    payload: BulkCreateSlotsRequest,
    parking_service: ParkingService = Depends(get_parking_service),
) -> BulkCreateSlotsResponse:
    return parking_service.create_slots_bulk(
        area_id=area_id,
        count=payload.count,
        prefix=payload.prefix,
        start_index=payload.start_index,
    )


@router.patch("/slots/{slot_id}", response_model=ParkingSlotResponse)
def update_slot(
    slot_id: str,
    payload: UpdateSlotRequest,
    parking_service: ParkingService = Depends(get_parking_service),
) -> ParkingSlotResponse:
    return parking_service.update_slot(slot_id, payload)


@router.get("/areas/{area_id}/slots", response_model=ParkingSlotListResponse)
def list_slots(
    area_id: str,
    parking_service: ParkingService = Depends(get_parking_service),
) -> ParkingSlotListResponse:
    return parking_service.list_slots(area_id)


@router.delete("/slots/{slot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_slot(
    slot_id: str,
    parking_service: ParkingService = Depends(get_parking_service),
):
    parking_service.delete_slot(slot_id)


# --- timeline / valet journey endpoints ---------------------------------

@router.get("/sessions/{session_id}/timeline", response_model=ParkingTimelineListResponse)
def get_session_timeline(
    session_id: str,
    timeline_service: TimelineService = Depends(get_timeline_service),
) -> ParkingTimelineListResponse:
    return timeline_service.get_timeline(session_id)


@router.post(
    "/sessions/{session_id}/timeline",
    response_model=ParkingTimelineEventResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_session_timeline_event(
    session_id: str,
    payload: CreateTimelineEventRequest,
    timeline_service: TimelineService = Depends(get_timeline_service),
) -> ParkingTimelineEventResponse:
    event = timeline_service.create_event_from_request(session_id, payload)
    logger.info(
        "timeline_event session_id=%s stage=%s", session_id, event.stage,
    )
    return event


@router.post("/sessions/{session_id}/accept-parking-request", response_model=ParkingTimelineEventResponse)
def accept_parking_request(
    session_id: str,
    payload: TimelineActionRequest = TimelineActionRequest(),
    timeline_service: TimelineService = Depends(get_timeline_service),
) -> ParkingTimelineEventResponse:
    return timeline_service.accept_parking_request(session_id, notes=payload.notes)


@router.post("/sessions/{session_id}/mark-parked", response_model=ParkingTimelineEventResponse)
def mark_parked(
    session_id: str,
    payload: TimelineActionRequest = TimelineActionRequest(),
    timeline_service: TimelineService = Depends(get_timeline_service),
) -> ParkingTimelineEventResponse:
    return timeline_service.mark_parked(session_id, notes=payload.notes)


@router.post("/sessions/{session_id}/request-delivery", response_model=ParkingTimelineEventResponse)
def request_delivery(
    session_id: str,
    payload: TimelineActionRequest = TimelineActionRequest(),
    timeline_service: TimelineService = Depends(get_timeline_service),
) -> ParkingTimelineEventResponse:
    return timeline_service.request_delivery(session_id, notes=payload.notes)


@router.post("/sessions/{session_id}/assign-for-delivery", response_model=ParkingTimelineEventResponse)
def assign_for_delivery(
    session_id: str,
    payload: TimelineActionRequest = TimelineActionRequest(),
    timeline_service: TimelineService = Depends(get_timeline_service),
) -> ParkingTimelineEventResponse:
    return timeline_service.assign_for_delivery(
        session_id, valet_id=payload.valet_id, valet_name=payload.valet_name, notes=payload.notes
    )


@router.post("/sessions/{session_id}/accept-delivery", response_model=ParkingTimelineEventResponse)
def accept_delivery(
    session_id: str,
    payload: TimelineActionRequest = TimelineActionRequest(),
    timeline_service: TimelineService = Depends(get_timeline_service),
) -> ParkingTimelineEventResponse:
    return timeline_service.accept_delivery(
        session_id, valet_id=payload.valet_id, valet_name=payload.valet_name, notes=payload.notes
    )


@router.post("/sessions/{session_id}/picked-up", response_model=ParkingTimelineEventResponse)
def picked_up(
    session_id: str,
    payload: TimelineActionRequest = TimelineActionRequest(),
    timeline_service: TimelineService = Depends(get_timeline_service),
) -> ParkingTimelineEventResponse:
    return timeline_service.picked_up(session_id, notes=payload.notes)


@router.post("/sessions/{session_id}/arrived", response_model=ParkingTimelineEventResponse)
def arrived(
    session_id: str,
    payload: TimelineActionRequest = TimelineActionRequest(),
    timeline_service: TimelineService = Depends(get_timeline_service),
) -> ParkingTimelineEventResponse:
    return timeline_service.arrived(session_id, notes=payload.notes)


@router.post("/sessions/{session_id}/manual-override", response_model=ParkingTimelineEventResponse)
def manual_override(
    session_id: str,
    payload: TimelineActionRequest = TimelineActionRequest(),
    timeline_service: TimelineService = Depends(get_timeline_service),
) -> ParkingTimelineEventResponse:
    return timeline_service.manual_override(session_id, notes=payload.notes)


@router.post("/sessions/{session_id}/delivered", response_model=ParkingTimelineEventResponse)
def delivered(
    session_id: str,
    payload: TimelineActionRequest = TimelineActionRequest(),
    timeline_service: TimelineService = Depends(get_timeline_service),
) -> ParkingTimelineEventResponse:
    event = timeline_service.deliver(session_id, notes=payload.notes)
    logger.info("parking_delivered session_id=%s", session_id)
    return event
