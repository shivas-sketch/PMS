"""Business layer for the valet parking timeline / journey workflow.

Orchestrates ``ParkingRepository`` (sessions/slots/areas/config) and
``TimelineRepository`` (immutable history events) so route handlers never
have to sequence the two themselves. Every convenience action here
(``picked_up``, ``deliver``, etc.) is just a thin wrapper around
``add_event`` plus, where the physical workflow demands it, a slot/exit
side-effect - so nothing here duplicates the transactional invariants
already enforced by the repositories.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.enums import ParkingTimelineStage
from app.exceptions import ParkingSessionNotFoundError, ParkingSlotRequiredError, VehicleAlreadyExitedError
from app.repositories.parking_repository import ParkingRepository
from app.repositories.timeline_repository import TimelineRepository
from app.schemas.parking import (
    CreateTimelineEventRequest,
    ParkingSessionResponse,
    ParkingTimelineEventResponse,
    ParkingTimelineListResponse,
)


class TimelineService:
    def __init__(self, parking_repository: ParkingRepository, timeline_repository: TimelineRepository):
        self.parking_repository = parking_repository
        self.timeline_repository = timeline_repository

    # --- helpers ----------------------------------------------------------
    def _get_session_or_404(self, session_id: str) -> dict:
        session = self.parking_repository.get_session(session_id)
        if session is None:
            raise ParkingSessionNotFoundError(f"Parking session '{session_id}' not found")
        return session

    # --- reads --------------------------------------------------------
    def get_timeline(self, session_id: str) -> ParkingTimelineListResponse:
        self._get_session_or_404(session_id)
        events = self.timeline_repository.get_session_timeline(session_id)
        items = [ParkingTimelineEventResponse.model_validate(e) for e in events]
        return ParkingTimelineListResponse(events=items, count=len(items))

    # --- generic event creation -----------------------------------------
    def add_event(
        self,
        session_id: str,
        stage: ParkingTimelineStage,
        valet_id: Optional[str] = None,
        valet_name: Optional[str] = None,
        notes: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ParkingTimelineEventResponse:
        session = self._get_session_or_404(session_id)
        if (
            stage == ParkingTimelineStage.PARKED
            and not session.get("slotId")
            and not session.get("isCorridorParking")
        ):
            raise ParkingSlotRequiredError()
        event = self.timeline_repository.create_timeline_event(
            session_id=session_id,
            vehicle_number=session.get("vehicleNumber"),
            stage=stage,
            area_id=session.get("areaId"),
            area_name=session.get("areaName"),
            slot_id=session.get("slotId"),
            slot_number=session.get("slotNumber"),
            valet_id=valet_id,
            valet_name=valet_name,
            notes=notes,
            metadata=metadata,
        )
        return ParkingTimelineEventResponse.model_validate(event)

    def create_event_from_request(
        self, session_id: str, request: CreateTimelineEventRequest
    ) -> ParkingTimelineEventResponse:
        return self.add_event(
            session_id,
            stage=request.stage,
            valet_id=request.valet_id,
            valet_name=request.valet_name,
            notes=request.notes,
            metadata=request.metadata,
        )

    # --- convenience workflow actions ------------------------------------
    # Each maps 1:1 onto a timeline stage; several also trigger a
    # repository side-effect (slot release, vehicle exit) so capacity and
    # slot counters stay correct without ever being adjusted twice.

    def accept_parking_request(self, session_id: str, notes: Optional[str] = None) -> ParkingTimelineEventResponse:
        return self.add_event(session_id, ParkingTimelineStage.PARKING_REQUEST_ACCEPTED, notes=notes)

    def mark_parked(self, session_id: str, notes: Optional[str] = None) -> ParkingTimelineEventResponse:
        return self.add_event(session_id, ParkingTimelineStage.PARKED, notes=notes)

    def request_delivery(self, session_id: str, notes: Optional[str] = None) -> ParkingTimelineEventResponse:
        return self.add_event(session_id, ParkingTimelineStage.REQUESTED_FOR_DELIVERY, notes=notes)

    def assign_for_delivery(
        self,
        session_id: str,
        valet_id: Optional[str] = None,
        valet_name: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> ParkingTimelineEventResponse:
        return self.add_event(
            session_id, ParkingTimelineStage.ASSIGNED_FOR_DELIVERY, valet_id=valet_id, valet_name=valet_name, notes=notes
        )

    def accept_delivery(
        self,
        session_id: str,
        valet_id: Optional[str] = None,
        valet_name: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> ParkingTimelineEventResponse:
        return self.add_event(
            session_id, ParkingTimelineStage.DELIVERY_REQUEST_ACCEPTED, valet_id=valet_id, valet_name=valet_name, notes=notes
        )

    def picked_up(self, session_id: str, notes: Optional[str] = None) -> ParkingTimelineEventResponse:
        # Record the event first (while the session still references the
        # slot the vehicle is being picked up from), then release the slot.
        session = self._get_session_or_404(session_id)
        event = self.add_event(session_id, ParkingTimelineStage.PICKED_UP, notes=notes)
        if session.get("slotId") or session.get("isCorridorParking"):
            self.parking_repository.release_slot_for_pickup(session_id)
        return event

    def arrived(self, session_id: str, notes: Optional[str] = None) -> ParkingTimelineEventResponse:
        return self.add_event(session_id, ParkingTimelineStage.ARRIVED, notes=notes)

    def manual_override(self, session_id: str, notes: Optional[str] = None) -> ParkingTimelineEventResponse:
        return self.add_event(session_id, ParkingTimelineStage.REQUESTED_FOR_MANUAL_OVERRIDE, notes=notes)

    def deliver(self, session_id: str, notes: Optional[str] = None) -> ParkingTimelineEventResponse:
        session = self._get_session_or_404(session_id)
        if session.get("status") == "EXITED":
            raise VehicleAlreadyExitedError()
        event = self.add_event(session_id, ParkingTimelineStage.DELIVERED, notes=notes)
        # exit_vehicle only releases slot/area counters if the session still
        # references a slot (i.e. `picked_up` was never called) - global
        # config counters are always adjusted exactly once, here.
        self.parking_repository.exit_vehicle(session.get("vehicleNumber"))
        return event
