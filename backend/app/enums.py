"""Shared enums for the parking domain.

``ParkingTimelineStage`` models the valet parking journey as an ordered
(but not strictly linear — stages can repeat) set of history events. See
``app.repositories.timeline_repository`` and ``app.services.timeline_service``
for how these are persisted and surfaced.
"""
from __future__ import annotations

from enum import Enum


class ParkingTimelineStage(str, Enum):
    ASSIGNED_FOR_PARKING = "ASSIGNED_FOR_PARKING"
    PARKING_REQUEST_ACCEPTED = "PARKING_REQUEST_ACCEPTED"
    PARKED = "PARKED"
    REQUESTED_FOR_DELIVERY = "REQUESTED_FOR_DELIVERY"
    ASSIGNED_FOR_DELIVERY = "ASSIGNED_FOR_DELIVERY"
    DELIVERY_REQUEST_ACCEPTED = "DELIVERY_REQUEST_ACCEPTED"
    PICKED_UP = "PICKED_UP"
    ARRIVED = "ARRIVED"
    REQUESTED_FOR_MANUAL_OVERRIDE = "REQUESTED_FOR_MANUAL_OVERRIDE"
    DELIVERED = "DELIVERED"


TIMELINE_STAGE_DISPLAY_NAMES: dict[ParkingTimelineStage, str] = {
    ParkingTimelineStage.ASSIGNED_FOR_PARKING: "Assigned for parking",
    ParkingTimelineStage.PARKING_REQUEST_ACCEPTED: "Parking request accepted",
    ParkingTimelineStage.PARKED: "Parked",
    ParkingTimelineStage.REQUESTED_FOR_DELIVERY: "Requested for delivery",
    ParkingTimelineStage.ASSIGNED_FOR_DELIVERY: "Assigned for delivery",
    ParkingTimelineStage.DELIVERY_REQUEST_ACCEPTED: "Delivery request accepted",
    ParkingTimelineStage.PICKED_UP: "Picked up",
    ParkingTimelineStage.ARRIVED: "Arrived",
    ParkingTimelineStage.REQUESTED_FOR_MANUAL_OVERRIDE: "Requested For Manual Override",
    ParkingTimelineStage.DELIVERED: "Delivered",
}


def get_stage_display_name(stage: "ParkingTimelineStage | str") -> str:
    if not isinstance(stage, ParkingTimelineStage):
        stage = ParkingTimelineStage(stage)
    return TIMELINE_STAGE_DISPLAY_NAMES[stage]
