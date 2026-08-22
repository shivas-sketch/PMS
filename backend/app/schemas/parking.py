"""Request/response contracts for the /api/parking/* endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import Field, field_validator

from app.enums import ParkingTimelineStage
from app.schemas.common import CamelModel
from app.utils.vehicle_number import clean_vehicle_number

SessionStatus = Literal["ACTIVE", "EXITED"]
AreaType = Literal["BASEMENT", "GROUND", "SIDE", "OUTSIDE", "ROOFTOP", "OTHER"]
SlotStatus = Literal["AVAILABLE", "OCCUPIED", "RESERVED", "MAINTENANCE"]


class AddVehicleRequest(CamelModel):
    vehicle_number: str = Field(..., min_length=1, max_length=20)
    wheel_category: int
    vehicle_type: str = Field(..., min_length=1, max_length=40)
    hospital_side: Optional[str] = Field(None, max_length=40)
    area_id: Optional[str] = None
    slot_id: Optional[str] = None

    @field_validator("vehicle_number")
    @classmethod
    def _clean_number(cls, value: str) -> str:
        cleaned = clean_vehicle_number(value)
        if not cleaned:
            raise ValueError("vehicleNumber must not be empty")
        return cleaned

    @field_validator("wheel_category")
    @classmethod
    def _valid_wheel_category(cls, value: int) -> int:
        if value not in (2, 3, 4, 6):
            raise ValueError("wheelCategory must be one of 2, 3, 4, 6")
        return value


class VehicleResponse(CamelModel):
    vehicle_number: str
    wheel_category: int
    vehicle_type: str
    created_at: datetime
    updated_at: datetime
    active_session_id: Optional[str] = None


class ParkingSessionResponse(CamelModel):
    session_id: str
    vehicle_number: str
    wheel_category: int
    vehicle_type: str
    hospital_side: Optional[str] = None
    status: SessionStatus
    entry_time: datetime
    exit_time: Optional[datetime] = None
    area_id: Optional[str] = None
    area_name: Optional[str] = None
    slot_id: Optional[str] = None
    slot_number: Optional[str] = None
    current_stage: Optional[ParkingTimelineStage] = None


class UpdateSessionRequest(CamelModel):
    vehicle_type: Optional[str] = Field(None, min_length=1, max_length=40)
    wheel_category: Optional[int] = None
    hospital_side: Optional[str] = Field(None, max_length=40)

    @field_validator("wheel_category")
    @classmethod
    def _valid_wheel_category(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value not in (2, 3, 4, 6):
            raise ValueError("wheelCategory must be one of 2, 3, 4, 6")
        return value


class CapacityResponse(CamelModel):
    total_capacity: int
    available_slots: int
    occupied_slots: int


class VehicleListResponse(CamelModel):
    vehicles: List[ParkingSessionResponse] = Field(default_factory=list)
    count: int = 0


class CreateAreaRequest(CamelModel):
    name: str = Field(..., min_length=1, max_length=60)
    area_type: AreaType = "OTHER"
    description: Optional[str] = Field(None, max_length=200)


class ParkingAreaResponse(CamelModel):
    area_id: str
    name: str
    area_type: AreaType
    description: Optional[str] = None
    total_slots: int = 0
    available_slots: int = 0
    occupied_slots: int = 0
    created_at: datetime
    updated_at: datetime


class ParkingAreaListResponse(CamelModel):
    areas: List[ParkingAreaResponse] = Field(default_factory=list)
    count: int = 0


class CreateSlotRequest(CamelModel):
    slot_number: str = Field(..., min_length=1, max_length=20)


class BulkCreateSlotsRequest(CamelModel):
    count: int = Field(..., ge=1, le=500, description="Number of slots to create")
    prefix: Optional[str] = Field(None, max_length=10, description="Optional prefix for auto-generated slot numbers (e.g. 'A' yields A1, A2, ...)")
    start_index: int = Field(1, ge=1, description="Starting index for auto-generated slot numbers")


class BulkCreateSlotsResponse(CamelModel):
    created: int
    slots: List[ParkingSlotResponse] = Field(default_factory=list)


class UpdateSlotRequest(CamelModel):
    slot_number: Optional[str] = Field(None, min_length=1, max_length=20)
    status: Optional[SlotStatus] = None


class ReassignSlotRequest(CamelModel):
    slot_id: str = Field(..., min_length=1)


class ParkingSlotResponse(CamelModel):
    slot_id: str
    area_id: str
    slot_number: str
    status: SlotStatus
    vehicle_number: Optional[str] = None
    session_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ParkingSlotListResponse(CamelModel):
    slots: List[ParkingSlotResponse] = Field(default_factory=list)
    count: int = 0


# --- timeline / valet journey -------------------------------------------

class CreateTimelineEventRequest(CamelModel):
    stage: ParkingTimelineStage
    valet_id: Optional[str] = None
    valet_name: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=500)
    metadata: Optional[Dict[str, Any]] = None


class TimelineActionRequest(CamelModel):
    """Body accepted by the convenience workflow-action endpoints.

    All fields are optional so ``POST .../picked-up`` etc. can be called
    with an empty body, while still allowing a valet id/name/notes to be
    attached when known.
    """

    valet_id: Optional[str] = None
    valet_name: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=500)
    metadata: Optional[Dict[str, Any]] = None


class ParkingTimelineEventResponse(CamelModel):
    event_id: str
    session_id: str
    vehicle_number: str
    stage: ParkingTimelineStage
    display_name: str
    timestamp: datetime
    area_id: Optional[str] = None
    area_name: Optional[str] = None
    slot_id: Optional[str] = None
    slot_number: Optional[str] = None
    valet_id: Optional[str] = None
    valet_name: Optional[str] = None
    notes: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ParkingTimelineListResponse(CamelModel):
    events: List[ParkingTimelineEventResponse] = Field(default_factory=list)
    count: int = 0
