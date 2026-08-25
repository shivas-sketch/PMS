"""Test doubles.

``FakeParkingRepository`` mirrors the public method signatures, return
shapes and exception types of ``app.repositories.parking_repository.ParkingRepository``
without touching Firestore, so ``ParkingService`` (and, via dependency
overrides, the HTTP layer) can be exercised deterministically and
concurrently in-process.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.enums import ParkingTimelineStage, get_stage_display_name
from app.exceptions import (
    AreaHasActiveSlotsError,
    DuplicateSlotError,
    ParkingAreaNotFoundError,
    ParkingFullError,
    ParkingSessionNotFoundError,
    SlotAlreadyOccupiedError,
    VehicleAlreadyActiveError,
    VehicleAlreadyExitedError,
    VehicleNotFoundError,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FakeParkingRepository:
    def __init__(self, total_capacity: int = 100):
        self._lock = threading.Lock()
        self._config: Dict = {
            "totalCapacity": total_capacity,
            "availableSlots": total_capacity,
            "occupiedSlots": 0,
            "sessionCounter": 0,
        }
        self._vehicles: Dict[str, dict] = {}
        self._sessions: Dict[str, dict] = {}
        self._areas: Dict[str, dict] = {}
        self._slots: Dict[str, dict] = {}

    def ensure_config(self, total_capacity: int = 100) -> None:
        pass  # already initialized in __init__ for the fake

    def get_capacity(self) -> dict:
        with self._lock:
            return dict(self._config)

    def get_vehicle(self, vehicle_number: str) -> Optional[dict]:
        with self._lock:
            vehicle = self._vehicles.get(vehicle_number)
            return dict(vehicle) if vehicle else None

    def get_session(self, session_id: str) -> Optional[dict]:
        with self._lock:
            session = self._sessions.get(session_id)
            return dict(session) if session else None

    def get_current_session_for_vehicle(self, vehicle_number: str) -> Optional[dict]:
        with self._lock:
            vehicle = self._vehicles.get(vehicle_number)
            if vehicle is None:
                return None
            session_id = vehicle.get("activeSessionId") or vehicle.get("lastSessionId")
            if not session_id:
                return None
            session = self._sessions.get(session_id)
            return dict(session) if session else None

    def update_session(
        self,
        session_id: str,
        vehicle_type: Optional[str] = None,
        wheel_category: Optional[int] = None,
        hospital_side: Optional[str] = None,
    ) -> dict:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise ParkingSessionNotFoundError(f"Parking session '{session_id}' not found")
            if session.get("status") == "EXITED":
                raise VehicleAlreadyExitedError(
                    f"Parking session '{session_id}' has exited and can no longer be edited"
                )
            if vehicle_type is not None:
                session["vehicleType"] = vehicle_type
            if wheel_category is not None:
                session["wheelCategory"] = wheel_category
            if hospital_side is not None:
                session["hospitalSide"] = hospital_side
            session["updatedAt"] = _utcnow()
            return dict(session)

    def list_sessions(self, status: Optional[str] = None, limit: int = 500) -> List[dict]:
        with self._lock:
            sessions = list(self._sessions.values())
        if status:
            sessions = [s for s in sessions if s.get("status") == status]
        sessions.sort(key=lambda s: s.get("entryTime") or _utcnow(), reverse=True)
        return [dict(s) for s in sessions[:limit]]

    def add_vehicle(self, vehicle_number: str, wheel_category: int, vehicle_type: str, hospital_side=None, area_id=None, slot_id=None) -> dict:
        with self._lock:
            available_slots = int(self._config.get("availableSlots", 0))
            if available_slots <= 0:
                raise ParkingFullError()

            vehicle = self._vehicles.get(vehicle_number)
            if vehicle and vehicle.get("activeSessionId"):
                raise VehicleAlreadyActiveError()

            now = _utcnow()
            session_counter = int(self._config.get("sessionCounter", 0)) + 1
            session_id = f"PS-{session_counter:06d}"

            area_name = None
            slot_number = None
            if slot_id and slot_id in self._slots:
                slot = self._slots[slot_id]
                if slot["status"] != "AVAILABLE":
                    raise SlotAlreadyOccupiedError()
                slot_number = slot["slotNumber"]
                area_id = slot["areaId"]
                slot["status"] = "OCCUPIED"
                slot["vehicleNumber"] = vehicle_number
                slot["sessionId"] = session_id
                slot["updatedAt"] = now
            if area_id and area_id in self._areas:
                area_name = self._areas[area_id]["name"]
                if slot_id:
                    self._areas[area_id]["availableSlots"] -= 1
                    self._areas[area_id]["occupiedSlots"] += 1

            session_payload = {
                "sessionId": session_id,
                "vehicleNumber": vehicle_number,
                "wheelCategory": wheel_category,
                "vehicleType": vehicle_type,
                "hospitalSide": hospital_side,
                "status": "ACTIVE",
                "entryTime": now,
                "exitTime": None,
                "areaId": area_id,
                "areaName": area_name,
                "slotId": slot_id,
                "slotNumber": slot_number,
                "currentStage": ParkingTimelineStage.ASSIGNED_FOR_PARKING.value,
                "updatedAt": now,
            }
            self._sessions[session_id] = session_payload

            self._vehicles[vehicle_number] = {
                "vehicleNumber": vehicle_number,
                "wheelCategory": wheel_category,
                "vehicleType": vehicle_type,
                "createdAt": vehicle.get("createdAt") if vehicle else now,
                "updatedAt": now,
                "activeSessionId": session_id,
                "lastSessionId": session_id,
            }

            self._config["availableSlots"] = available_slots - 1
            self._config["occupiedSlots"] = int(self._config.get("occupiedSlots", 0)) + 1
            self._config["sessionCounter"] = session_counter

            return dict(session_payload)

    def exit_vehicle(self, vehicle_number: str) -> dict:
        with self._lock:
            vehicle = self._vehicles.get(vehicle_number)
            if vehicle is None:
                raise VehicleNotFoundError(f"Vehicle '{vehicle_number}' has no parking history")

            active_session_id = vehicle.get("activeSessionId")
            if not active_session_id:
                raise VehicleAlreadyExitedError()

            now = _utcnow()
            session = self._sessions[active_session_id]
            session["status"] = "EXITED"
            session["exitTime"] = now

            vehicle["activeSessionId"] = None
            vehicle["updatedAt"] = now

            # Release slot if assigned
            slot_id = session.get("slotId")
            area_id = session.get("areaId")
            if slot_id and slot_id in self._slots:
                self._slots[slot_id]["status"] = "AVAILABLE"
                self._slots[slot_id]["vehicleNumber"] = None
                self._slots[slot_id]["sessionId"] = None
                self._slots[slot_id]["updatedAt"] = now
                if area_id and area_id in self._areas:
                    self._areas[area_id]["availableSlots"] += 1
                    self._areas[area_id]["occupiedSlots"] = max(0, self._areas[area_id]["occupiedSlots"] - 1)

            self._config["availableSlots"] = int(self._config.get("availableSlots", 0)) + 1
            self._config["occupiedSlots"] = max(0, int(self._config.get("occupiedSlots", 0)) - 1)

            return dict(session)

    def release_slot_for_pickup(self, session_id: str) -> dict:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise ParkingSessionNotFoundError(f"Parking session '{session_id}' not found")

            slot_id = session.get("slotId")
            area_id = session.get("areaId")
            if not slot_id:
                return dict(session)

            now = _utcnow()
            if slot_id in self._slots:
                self._slots[slot_id]["status"] = "AVAILABLE"
                self._slots[slot_id]["vehicleNumber"] = None
                self._slots[slot_id]["sessionId"] = None
                self._slots[slot_id]["updatedAt"] = now
            if area_id and area_id in self._areas:
                self._areas[area_id]["availableSlots"] += 1
                self._areas[area_id]["occupiedSlots"] = max(0, self._areas[area_id]["occupiedSlots"] - 1)
                self._areas[area_id]["updatedAt"] = now

            session["slotId"] = None
            session["slotNumber"] = None
            session["areaId"] = None
            session["areaName"] = None
            return dict(session)

    # --- parking areas & slots (fake) -----------------------------------
    def create_area(self, name: str, area_type: str = "OTHER", description=None) -> dict:
        with self._lock:
            now = _utcnow()
            area_id = f"area-{len(self._areas) + 1}"
            payload = {
                "areaId": area_id,
                "name": name,
                "areaType": area_type,
                "description": description,
                "totalSlots": 0,
                "availableSlots": 0,
                "occupiedSlots": 0,
                "createdAt": now,
                "updatedAt": now,
            }
            self._areas[area_id] = payload
            return dict(payload)

    def list_areas(self) -> list:
        with self._lock:
            return [dict(a) for a in self._areas.values()]

    def get_area(self, area_id: str):
        with self._lock:
            area = self._areas.get(area_id)
            return dict(area) if area else None

    def delete_area(self, area_id: str) -> None:
        with self._lock:
            if area_id not in self._areas:
                raise ParkingAreaNotFoundError()
            if self._areas[area_id].get("occupiedSlots", 0) > 0:
                raise AreaHasActiveSlotsError()
            for sid, slot in list(self._slots.items()):
                if slot["areaId"] == area_id:
                    del self._slots[sid]
            del self._areas[area_id]

    def create_slot(self, area_id: str, slot_number: str) -> dict:
        with self._lock:
            if area_id not in self._areas:
                raise ParkingAreaNotFoundError()
            for slot in self._slots.values():
                if slot["areaId"] == area_id and slot["slotNumber"] == slot_number:
                    raise DuplicateSlotError()
            now = _utcnow()
            slot_id = f"slot-{len(self._slots) + 1}"
            payload = {
                "slotId": slot_id,
                "areaId": area_id,
                "slotNumber": slot_number,
                "status": "AVAILABLE",
                "vehicleNumber": None,
                "sessionId": None,
                "createdAt": now,
                "updatedAt": now,
            }
            self._slots[slot_id] = payload
            self._areas[area_id]["totalSlots"] += 1
            self._areas[area_id]["availableSlots"] += 1
            self._areas[area_id]["updatedAt"] = now
            return dict(payload)

    def list_slots(self, area_id: str) -> list:
        with self._lock:
            slots = [dict(s) for s in self._slots.values() if s["areaId"] == area_id]
            area = self._areas.get(area_id)
            if area and area.get("corridorCapacity", 0) > 0:
                corridor_sessions = sorted(
                    [
                        dict(s)
                        for s in self._sessions.values()
                        if s.get("areaId") == area_id
                        and s.get("status") == "ACTIVE"
                        and s.get("isCorridorParking") is True
                    ],
                    key=lambda s: s.get("entryTime") or _utcnow().isoformat(),
                )
                vehicles = [(s.get("sessionId"), s.get("vehicleNumber")) for s in corridor_sessions]
                now = _utcnow()
                for i in range(1, area["corridorCapacity"] + 1):
                    session_id, vehicle_number = vehicles[i - 1] if i <= len(vehicles) else (None, None)
                    slots.append({
                        "slotId": f"{area_id}:corridor:{i}",
                        "areaId": area_id,
                        "slotNumber": f"corridor-{i}",
                        "status": "OCCUPIED" if i <= area.get("corridorOccupied", 0) else "AVAILABLE",
                        "vehicleNumber": vehicle_number,
                        "sessionId": session_id,
                        "createdAt": area.get("createdAt") or now,
                        "updatedAt": area.get("updatedAt") or now,
                        "isCorridorSlot": True,
                    })
            return slots

    def delete_slot(self, slot_id: str) -> None:
        with self._lock:
            if slot_id not in self._slots:
                from app.exceptions import ParkingSlotNotFoundError
                raise ParkingSlotNotFoundError()
            slot = self._slots[slot_id]
            if slot["status"] == "OCCUPIED":
                raise SlotAlreadyOccupiedError()
            area_id = slot["areaId"]
            del self._slots[slot_id]
            if area_id in self._areas:
                self._areas[area_id]["totalSlots"] -= 1
                self._areas[area_id]["availableSlots"] -= 1

    def reassign_slot(self, vehicle_number: str, new_slot_id: str) -> dict:
        with self._lock:
            from app.exceptions import ParkingSlotNotFoundError

            vehicle = self._vehicles.get(vehicle_number)
            if vehicle is None:
                raise VehicleNotFoundError(f"Vehicle '{vehicle_number}' not found")

            active_session_id = vehicle.get("activeSessionId")
            if not active_session_id:
                raise VehicleAlreadyExitedError()

            session = self._sessions[active_session_id]

            new_slot = self._slots.get(new_slot_id)
            if new_slot is None:
                raise ParkingSlotNotFoundError()
            if new_slot["status"] != "AVAILABLE":
                raise SlotAlreadyOccupiedError("Selected slot is not available")

            now = _utcnow()
            old_slot_id = session.get("slotId")
            old_area_id = session.get("areaId")
            new_area_id = new_slot["areaId"]
            new_slot_number = new_slot["slotNumber"]
            new_area_name = self._areas.get(new_area_id, {}).get("name") if new_area_id else None
            same_area = old_area_id == new_area_id

            # Free old slot
            if old_slot_id and old_slot_id in self._slots:
                self._slots[old_slot_id]["status"] = "AVAILABLE"
                self._slots[old_slot_id]["vehicleNumber"] = None
                self._slots[old_slot_id]["sessionId"] = None
                self._slots[old_slot_id]["updatedAt"] = now

            # Occupy new slot
            new_slot["status"] = "OCCUPIED"
            new_slot["vehicleNumber"] = vehicle_number
            new_slot["sessionId"] = active_session_id
            new_slot["updatedAt"] = now

            # Update session
            session["slotId"] = new_slot_id
            session["slotNumber"] = new_slot_number
            session["areaId"] = new_area_id
            session["areaName"] = new_area_name

            # Update area counters
            if old_slot_id and old_area_id and old_area_id in self._areas and not same_area:
                self._areas[old_area_id]["availableSlots"] += 1
                self._areas[old_area_id]["occupiedSlots"] = max(0, self._areas[old_area_id]["occupiedSlots"] - 1)
                self._areas[old_area_id]["updatedAt"] = now

            if new_area_id and new_area_id in self._areas and not (same_area and old_slot_id):
                self._areas[new_area_id]["availableSlots"] = max(0, self._areas[new_area_id]["availableSlots"] - 1)
                self._areas[new_area_id]["occupiedSlots"] += 1
                self._areas[new_area_id]["updatedAt"] = now

            return dict(session)


class FakeTimelineRepository:
    """In-memory mirror of ``app.repositories.timeline_repository.TimelineRepository``.

    Shares the same session dict as the ``FakeParkingRepository`` instance
    it is constructed with, so ``currentStage`` updates made here are
    visible through ``ParkingRepository.get_session``/``get_current_session_for_vehicle``
    - matching the real Firestore behaviour where both live on the same
    ``parking_sessions/{sessionId}`` document.
    """

    def __init__(self, parking_repository: "FakeParkingRepository"):
        self._parking_repository = parking_repository
        self._lock = threading.Lock()
        self._events: Dict[str, List[dict]] = {}
        self._counter = 0

    def get_session_timeline(self, session_id: str) -> List[dict]:
        with self._lock:
            events = list(self._events.get(session_id, []))
        return sorted([dict(e) for e in events], key=lambda e: e["timestamp"])

    def create_timeline_event(
        self,
        session_id: str,
        vehicle_number: str,
        stage,
        area_id: Optional[str] = None,
        area_name: Optional[str] = None,
        slot_id: Optional[str] = None,
        slot_number: Optional[str] = None,
        valet_id: Optional[str] = None,
        valet_name: Optional[str] = None,
        notes: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        with self._lock:
            session = self._parking_repository._sessions.get(session_id)
            if session is None:
                raise ParkingSessionNotFoundError(f"Parking session '{session_id}' not found")

            self._counter += 1
            stage_value = stage.value if isinstance(stage, ParkingTimelineStage) else stage
            now = _utcnow()
            payload = {
                "eventId": f"evt-{self._counter}",
                "sessionId": session_id,
                "vehicleNumber": vehicle_number,
                "stage": stage_value,
                "displayName": get_stage_display_name(stage_value),
                "timestamp": now,
                "areaId": area_id,
                "areaName": area_name,
                "slotId": slot_id,
                "slotNumber": slot_number,
                "valetId": valet_id,
                "valetName": valet_name,
                "notes": notes,
                "metadata": metadata,
            }
            self._events.setdefault(session_id, []).append(payload)
            session["currentStage"] = stage_value
            session["updatedAt"] = now
            return dict(payload)

    def update_current_stage(self, session_id: str, stage) -> None:
        with self._lock:
            session = self._parking_repository._sessions.get(session_id)
            if session is None:
                raise ParkingSessionNotFoundError(f"Parking session '{session_id}' not found")
            stage_value = stage.value if isinstance(stage, ParkingTimelineStage) else stage
            session["currentStage"] = stage_value
            session["updatedAt"] = _utcnow()
