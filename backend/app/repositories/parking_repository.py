"""Firestore-backed persistence for parking capacity, vehicles and sessions.

Collections
-----------
``parking_config/main``
    Singleton document holding capacity counters only - no per-slot
    (A1/A2/...) documents are ever created.
``vehicles/{vehicleNumber}``
    One document per plate. Tracks ``activeSessionId`` so duplicate/active
    checks and exit validation are single-document reads - no composite
    Firestore indexes are required anywhere in this repository.
``parking_sessions/{sessionId}``
    One document per entry/exit cycle, ``status`` is ``ACTIVE`` or
    ``EXITED``.

All capacity-mutating operations run inside a single Firestore transaction
so concurrent requests can never overbook capacity or double-release a
slot.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from google.cloud import firestore

from app.enums import ParkingTimelineStage
from app.exceptions import (
    AreaHasActiveSlotsError,
    CorridorFullError,
    DuplicateSlotError,
    InvalidCorridorCapacityError,
    ParkingAreaNotFoundError,
    ParkingConfigMissingError,
    ParkingFullError,
    ParkingSessionNotFoundError,
    ParkingSlotNotFoundError,
    SlotAlreadyOccupiedError,
    VehicleAlreadyActiveError,
    VehicleAlreadyExitedError,
    VehicleNotFoundError,
)
from app.utils.vehicle_number import clean_vehicle_number

CONFIG_COLLECTION = "parking_config"
CONFIG_DOC_ID = "main"
VEHICLES_COLLECTION = "vehicles"
SESSIONS_COLLECTION = "parking_sessions"
AREAS_COLLECTION = "parking_areas"
SLOTS_COLLECTION = "parking_slots"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ParkingRepository:
    def __init__(self, db: firestore.Client):
        self.db = db

    # --- references -------------------------------------------------
    @property
    def _config_ref(self):
        return self.db.collection(CONFIG_COLLECTION).document(CONFIG_DOC_ID)

    def _vehicle_ref(self, vehicle_number: str):
        return self.db.collection(VEHICLES_COLLECTION).document(vehicle_number)

    @property
    def _sessions_ref(self):
        return self.db.collection(SESSIONS_COLLECTION)

    def _session_ref(self, session_id: str):
        return self._sessions_ref.document(session_id)

    def _areas_ref(self):
        return self.db.collection(AREAS_COLLECTION)

    def _area_ref(self, area_id: str):
        return self._areas_ref().document(area_id)

    def _slots_ref(self):
        return self.db.collection(SLOTS_COLLECTION)

    def _slot_ref(self, slot_id: str):
        return self._slots_ref().document(slot_id)

    # --- bootstrap ----------------------------------------------------
    def ensure_config(self, total_capacity: int = 100, timeout: float = 10.0) -> None:
        """Create ``parking_config/main`` if it does not exist yet, then sync.

        Called once during app startup (see ``app.main``'s lifespan).
        ``retry=None`` + a short ``timeout`` deliberately disables
        google-api-core's default retry policy for this one call: that
        policy retries for up to its own (much longer than 10s) total
        deadline, so with it enabled an unreachable Firestore/emulator
        target hangs server startup for a long time instead of failing
        fast with a clear, actionable error.
        """
        snapshot = self._config_ref.get(timeout=timeout, retry=None)
        if not snapshot.exists:
            self._config_ref.set(
                {
                    "totalCapacity": total_capacity,
                    "availableSlots": total_capacity,
                    "occupiedSlots": 0,
                    "sessionCounter": 0,
                },
                timeout=timeout,
                retry=None,
            )
        self.sync_global_config()

    def sync_global_config(self) -> None:
        """Reconcile ``parking_config/main`` counters with actual data.

        Total capacity is the number of configured slots. Occupancy is the
        number of active sessions (a vehicle counts as on-site even if it has
        not been assigned a physical slot yet, e.g. ``ASSIGNED_FOR_PARKING``).
        Available is the difference.

        Called at startup after ``ensure_config`` as a safeguard against drift
        caused by manual edits, emulator resets, or bugs in incremental updates.
        """
        slots = list(self._slots_ref().stream())
        numbered_total = len(slots)

        areas = list(self._areas_ref().stream())
        corridor_total = sum(int((a.to_dict() or {}).get("corridorCapacity", 0) or 0) for a in areas)
        total = numbered_total + corridor_total

        active_sessions = list(self._sessions_ref.where("status", "==", "ACTIVE").stream())
        occupied = len(active_sessions)

        config_snapshot = self._config_ref.get()
        if not config_snapshot.exists:
            return
        config = config_snapshot.to_dict()

        # If no slots have been created yet, keep the configured total so the
        # default capacity is still honored.
        if total == 0:
            total = int(config.get("totalCapacity", 0))

        available = total - occupied

        updates: dict = {}
        if config.get("totalCapacity") != total:
            updates["totalCapacity"] = total
        if config.get("availableSlots") != available:
            updates["availableSlots"] = available
        if config.get("occupiedSlots") != occupied:
            updates["occupiedSlots"] = occupied

        if updates:
            self._config_ref.update(updates)

    # --- reads ----------------------------------------------------------
    def get_capacity(self) -> dict:
        snapshot = self._config_ref.get()
        if not snapshot.exists:
            raise ParkingConfigMissingError()
        return snapshot.to_dict()

    def get_vehicle(self, vehicle_number: str) -> Optional[dict]:
        snapshot = self._vehicle_ref(vehicle_number).get()
        if not snapshot.exists:
            return None
        return snapshot.to_dict()

    def get_session(self, session_id: str) -> Optional[dict]:
        snapshot = self._session_ref(session_id).get()
        if not snapshot.exists:
            return None
        return snapshot.to_dict()

    def get_current_session_for_vehicle(self, vehicle_number: str) -> Optional[dict]:
        """Active session if parked, otherwise the most recent session, else None."""
        vehicle = self.get_vehicle(vehicle_number)
        if vehicle is None:
            return None
        session_id = vehicle.get("activeSessionId") or vehicle.get("lastSessionId")
        if not session_id:
            return None
        return self.get_session(session_id)

    def update_session(
        self,
        session_id: str,
        vehicle_type: Optional[str] = None,
        wheel_category: Optional[int] = None,
        hospital_side: Optional[str] = None,
    ) -> dict:
        snapshot = self._session_ref(session_id).get()
        if not snapshot.exists:
            raise ParkingSessionNotFoundError(f"Parking session '{session_id}' not found")
        session = snapshot.to_dict()
        if session.get("status") == "EXITED":
            raise VehicleAlreadyExitedError(
                f"Parking session '{session_id}' has exited and can no longer be edited"
            )
        updates: dict = {"updatedAt": _utcnow()}
        if vehicle_type is not None:
            updates["vehicleType"] = vehicle_type
        if wheel_category is not None:
            updates["wheelCategory"] = wheel_category
        if hospital_side is not None:
            updates["hospitalSide"] = hospital_side
        self._session_ref(session_id).update(updates)
        session.update(updates)
        return session

    def list_sessions(self, status: Optional[str] = None, limit: int = 500) -> List[dict]:
        query = self._sessions_ref
        if status:
            query = query.where("status", "==", status)
        docs = list(query.limit(limit).stream())
        sessions = [doc.to_dict() for doc in docs]
        sessions.sort(key=lambda s: s.get("entryTime") or _utcnow(), reverse=True)
        return sessions

    # --- mutations (transactional) --------------------------------------
    def add_vehicle(
        self,
        vehicle_number: str,
        wheel_category: int,
        vehicle_type: str,
        hospital_side: Optional[str] = None,
        area_id: Optional[str] = None,
        slot_id: Optional[str] = None,
        use_corridor: bool = False,
    ) -> dict:
        cleaned = clean_vehicle_number(vehicle_number)
        transaction = self.db.transaction()
        return _add_vehicle_txn(
            transaction, self, cleaned, wheel_category, vehicle_type, hospital_side, area_id, slot_id, use_corridor
        )

    def exit_vehicle(self, vehicle_number: str) -> dict:
        cleaned = clean_vehicle_number(vehicle_number)
        transaction = self.db.transaction()
        return _exit_vehicle_txn(transaction, self, cleaned)

    def reassign_slot(self, vehicle_number: str, new_slot_id: str) -> dict:
        cleaned = clean_vehicle_number(vehicle_number)
        transaction = self.db.transaction()
        return _reassign_slot_txn(transaction, self, cleaned, new_slot_id)

    def release_slot_for_pickup(self, session_id: str) -> dict:
        """Free a session's slot/area occupancy when a valet picks up the vehicle.

        Deliberately does NOT touch ``parking_config/main`` global counters:
        the vehicle is still on-site (with the valet) until it is actually
        delivered/exited, so global capacity is only adjusted at that point
        (see ``_exit_vehicle_txn``). This avoids double-counting slot/area
        and global capacity release for the same vehicle.
        """
        transaction = self.db.transaction()
        return _release_slot_for_pickup_txn(transaction, self, session_id)

    # --- parking areas --------------------------------------------------
    def create_area(
        self,
        name: str,
        area_type: str,
        description: Optional[str] = None,
        corridor_capacity: int = 0,
    ) -> dict:
        now = _utcnow()
        doc_ref = self._areas_ref().document()
        area_id = doc_ref.id
        corridor_capacity = max(0, int(corridor_capacity or 0))
        payload = {
            "areaId": area_id,
            "name": name,
            "areaType": area_type,
            "description": description,
            "totalSlots": 0,
            "availableSlots": 0,
            "occupiedSlots": 0,
            "corridorCapacity": corridor_capacity,
            "corridorAvailable": corridor_capacity,
            "corridorOccupied": 0,
            "createdAt": now,
            "updatedAt": now,
        }
        doc_ref.set(payload)
        if corridor_capacity > 0:
            self._config_ref.update({
                "totalCapacity": firestore.Increment(corridor_capacity),
                "availableSlots": firestore.Increment(corridor_capacity),
            })
        return payload

    def list_areas(self) -> List[dict]:
        docs = list(self._areas_ref().order_by("createdAt").stream())
        return [doc.to_dict() for doc in docs]

    def get_area(self, area_id: str) -> Optional[dict]:
        snapshot = self._area_ref(area_id).get()
        if not snapshot.exists:
            return None
        return snapshot.to_dict()

    def delete_area(self, area_id: str) -> None:
        area_snapshot = self._area_ref(area_id).get()
        if not area_snapshot.exists:
            raise ParkingAreaNotFoundError()
        area = area_snapshot.to_dict()
        if area.get("occupiedSlots", 0) > 0:
            raise AreaHasActiveSlotsError()
        if area.get("corridorOccupied", 0) > 0:
            raise AreaHasActiveSlotsError("Cannot delete area with occupied corridor parking")
        slot_docs = list(self._slots_ref().where("areaId", "==", area_id).stream())
        for doc in slot_docs:
            doc.reference.delete()
        self._area_ref(area_id).delete()
        total_slots = int(area.get("totalSlots", 0))
        corridor_capacity = int(area.get("corridorCapacity", 0))
        total_release = total_slots + corridor_capacity
        if total_release > 0:
            self._config_ref.update({
                "totalCapacity": firestore.Increment(-total_release),
                "availableSlots": firestore.Increment(-total_release),
            })

    def update_area_corridor_capacity(self, area_id: str, corridor_capacity: int) -> dict:
        area_ref = self._area_ref(area_id)
        snapshot = area_ref.get()
        if not snapshot.exists:
            raise ParkingAreaNotFoundError()
        area = snapshot.to_dict()
        corridor_capacity = max(0, int(corridor_capacity))
        current_capacity = int(area.get("corridorCapacity", 0))
        current_occupied = int(area.get("corridorOccupied", 0))
        if corridor_capacity < current_occupied:
            raise InvalidCorridorCapacityError()
        delta = corridor_capacity - current_capacity
        now = _utcnow()
        updates = {
            "corridorCapacity": corridor_capacity,
            "corridorAvailable": corridor_capacity - current_occupied,
            "updatedAt": now,
        }
        area_ref.update(updates)
        if delta != 0:
            self._config_ref.update({
                "totalCapacity": firestore.Increment(delta),
                "availableSlots": firestore.Increment(delta),
            })
        area.update(updates)
        return area

    # --- parking slots --------------------------------------------------
    def create_slot(self, area_id: str, slot_number: str) -> dict:
        area_snapshot = self._area_ref(area_id).get()
        if not area_snapshot.exists:
            raise ParkingAreaNotFoundError()
        existing = list(
            self._slots_ref()
            .where("areaId", "==", area_id)
            .where("slotNumber", "==", slot_number)
            .limit(1)
            .stream()
        )
        if existing:
            raise DuplicateSlotError()
        now = _utcnow()
        doc_ref = self._slots_ref().document()
        slot_id = doc_ref.id
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
        doc_ref.set(payload)
        self._area_ref(area_id).update({
            "totalSlots": firestore.Increment(1),
            "availableSlots": firestore.Increment(1),
            "updatedAt": now,
        })
        self._config_ref.update({
            "totalCapacity": firestore.Increment(1),
            "availableSlots": firestore.Increment(1),
        })
        return payload

    def list_slots(self, area_id: str) -> List[dict]:
        area_snapshot = self._area_ref(area_id).get()
        area = area_snapshot.to_dict() if area_snapshot.exists else None

        docs = list(self._slots_ref().where("areaId", "==", area_id).stream())
        regular_slots = [doc.to_dict() for doc in docs]
        regular_slots.sort(key=lambda s: s.get("slotNumber", ""))

        corridor_slots: List[dict] = []
        if area and int(area.get("corridorCapacity", 0)) > 0:
            now = _utcnow()
            area_created_at = area.get("createdAt") or now
            area_updated_at = area.get("updatedAt") or now

            # Map active corridor-parked sessions in this area to numbered
            # references (1, 2, ...). The number is just a display reference so
            # the layout table can show corridor occupancy. We query by areaId
            # only and filter the rest in Python to avoid needing a new
            # composite Firestore index.
            corridor_sessions = sorted(
                [
                    s.to_dict()
                    for s in self._sessions_ref.where("areaId", "==", area_id).stream()
                    if (s.to_dict() or {}).get("status") == "ACTIVE"
                    and (s.to_dict() or {}).get("isCorridorParking") is True
                ],
                key=lambda s: s.get("entryTime") or _utcnow().isoformat(),
            )
            corridor_vehicles = [
                (s.get("sessionId"), s.get("vehicleNumber")) for s in corridor_sessions
            ]
            corridor_capacity = int(area.get("corridorCapacity", 0))

            for i in range(1, corridor_capacity + 1):
                session_id, vehicle_number = corridor_vehicles[i - 1] if i <= len(corridor_vehicles) else (None, None)
                corridor_slots.append({
                    "slotId": f"{area_id}:corridor:{i}",
                    "areaId": area_id,
                    "slotNumber": str(i),
                    "status": "OCCUPIED" if i <= area.get("corridorOccupied", 0) else "AVAILABLE",
                    "vehicleNumber": vehicle_number,
                    "sessionId": session_id,
                    "createdAt": area_created_at,
                    "updatedAt": area_updated_at,
                    "isCorridorSlot": True,
                })
            corridor_slots.sort(key=lambda s: s.get("slotNumber", ""))

        # Keep regular slots first, then corridor slots, so numbering is not
        # interleaved with any numeric physical slot names.
        return regular_slots + corridor_slots

    def delete_slot(self, slot_id: str) -> None:
        snapshot = self._slot_ref(slot_id).get()
        if not snapshot.exists:
            raise ParkingSlotNotFoundError()
        slot = snapshot.to_dict()
        if slot.get("status") == "OCCUPIED":
            raise SlotAlreadyOccupiedError()
        self._slot_ref(slot_id).delete()
        now = _utcnow()
        self._area_ref(slot["areaId"]).update({
            "totalSlots": firestore.Increment(-1),
            "availableSlots": firestore.Increment(-1),
            "updatedAt": now,
        })
        self._config_ref.update({
            "totalCapacity": firestore.Increment(-1),
            "availableSlots": firestore.Increment(-1),
        })

    def _get_existing_slot_numbers(self, area_id: str) -> set[str]:
        docs = list(self._slots_ref().where("areaId", "==", area_id).stream())
        return {doc.to_dict().get("slotNumber", "") for doc in docs}

    def create_slots_bulk(
        self,
        area_id: str,
        count: int,
        prefix: Optional[str] = None,
        start_index: int = 1,
    ) -> List[dict]:
        """Create *count* slots in a single batch write with auto-assigned numbers.

        Slot numbers are generated as ``{prefix}{index}`` (e.g. ``A1``, ``A2``
        or just ``1``, ``2`` if no prefix). Existing slot numbers in the area
        are checked to avoid duplicates; the start index is advanced past any
        collisions.
        """
        area_snapshot = self._area_ref(area_id).get()
        if not area_snapshot.exists:
            raise ParkingAreaNotFoundError()

        existing_numbers = self._get_existing_slot_numbers(area_id)
        now = _utcnow()
        batch = self.db.batch()
        created: List[dict] = []
        idx = start_index
        prefix_str = prefix or ""

        while len(created) < count:
            slot_number = f"{prefix_str}{idx}"
            if slot_number in existing_numbers:
                idx += 1
                continue

            doc_ref = self._slots_ref().document()
            slot_id = doc_ref.id
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
            batch.set(doc_ref, payload)
            existing_numbers.add(slot_number)
            created.append(payload)
            idx += 1

        batch.commit()

        self._area_ref(area_id).update({
            "totalSlots": firestore.Increment(count),
            "availableSlots": firestore.Increment(count),
            "updatedAt": now,
        })
        self._config_ref.update({
            "totalCapacity": firestore.Increment(count),
            "availableSlots": firestore.Increment(count),
        })
        return created

    def update_slot(
        self,
        slot_id: str,
        slot_number: Optional[str] = None,
        status: Optional[str] = None,
    ) -> dict:
        snapshot = self._slot_ref(slot_id).get()
        if not snapshot.exists:
            raise ParkingSlotNotFoundError()
        slot = snapshot.to_dict()

        if slot.get("status") == "OCCUPIED" and slot_number is not None:
            raise SlotAlreadyOccupiedError("Cannot rename an occupied slot")

        if slot_number is not None and slot_number != slot.get("slotNumber"):
            existing = list(
                self._slots_ref()
                .where("areaId", "==", slot["areaId"])
                .where("slotNumber", "==", slot_number)
                .limit(1)
                .stream()
            )
            if existing:
                raise DuplicateSlotError()

        updates: dict = {"updatedAt": _utcnow()}
        if slot_number is not None:
            updates["slotNumber"] = slot_number
        if status is not None:
            if slot.get("status") == "OCCUPIED" and status != "OCCUPIED":
                raise SlotAlreadyOccupiedError("Cannot change status of an occupied slot via update; use vehicle exit")
            updates["status"] = status

        self._slot_ref(slot_id).update(updates)
        slot.update(updates)
        return slot


@firestore.transactional
def _add_vehicle_txn(
    transaction: firestore.Transaction,
    repo: ParkingRepository,
    vehicle_number: str,
    wheel_category: int,
    vehicle_type: str,
    hospital_side: Optional[str] = None,
    area_id: Optional[str] = None,
    slot_id: Optional[str] = None,
    use_corridor: bool = False,
) -> dict:
    config_ref = repo._config_ref
    vehicle_ref = repo._vehicle_ref(vehicle_number)

    # --- reads (must all happen before any write in a Firestore transaction) ---
    config_snapshot = config_ref.get(transaction=transaction)
    vehicle_snapshot = vehicle_ref.get(transaction=transaction)

    if not config_snapshot.exists:
        raise ParkingConfigMissingError()
    config = config_snapshot.to_dict()

    available_slots = int(config.get("availableSlots", 0))
    if available_slots <= 0:
        raise ParkingFullError()

    vehicle = vehicle_snapshot.to_dict() if vehicle_snapshot.exists else None
    if vehicle and vehicle.get("activeSessionId"):
        raise VehicleAlreadyActiveError()

    # Corridor parking (unnumbered overflow capacity) is mutually exclusive
    # with a specific numbered slot and requires an area to be specified.
    use_corridor = bool(use_corridor) and not slot_id

    # --- slot validation (if area/slot specified) ---
    slot_snapshot = None
    area_snapshot = None
    area_name = None
    slot_number = None

    if slot_id:
        slot_ref = repo._slot_ref(slot_id)
        slot_snapshot = slot_ref.get(transaction=transaction)
        if not slot_snapshot.exists:
            raise ParkingSlotNotFoundError()
        slot_data = slot_snapshot.to_dict()
        if slot_data.get("status") != "AVAILABLE":
            raise SlotAlreadyOccupiedError()
        slot_number = slot_data.get("slotNumber")
        area_id = slot_data.get("areaId")

    if area_id:
        area_ref = repo._area_ref(area_id)
        area_snapshot = area_ref.get(transaction=transaction)
        if not area_snapshot.exists:
            raise ParkingAreaNotFoundError()
        area_data = area_snapshot.to_dict()
        area_name = area_data.get("name")

        if use_corridor:
            corridor_available = int(area_data.get("corridorAvailable", 0))
            if corridor_available <= 0:
                raise CorridorFullError()
            slot_number = "Corridor"
    elif use_corridor:
        # Corridor parking requires a specific area; silently ignore otherwise.
        use_corridor = False

    # --- writes -----------------------------------------------------------
    now = _utcnow()
    session_counter = int(config.get("sessionCounter", 0)) + 1
    session_id = f"PS-{session_counter:06d}"
    session_ref = repo._session_ref(session_id)

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
        "isCorridorParking": use_corridor,
        "currentStage": ParkingTimelineStage.ASSIGNED_FOR_PARKING.value,
        "updatedAt": now,
    }
    transaction.set(session_ref, session_payload)

    transaction.set(
        vehicle_ref,
        {
            "vehicleNumber": vehicle_number,
            "wheelCategory": wheel_category,
            "vehicleType": vehicle_type,
            "createdAt": vehicle.get("createdAt") if vehicle else now,
            "updatedAt": now,
            "activeSessionId": session_id,
            "lastSessionId": session_id,
        },
        merge=True,
    )

    transaction.update(
        config_ref,
        {
            "availableSlots": available_slots - 1,
            "occupiedSlots": int(config.get("occupiedSlots", 0)) + 1,
            "sessionCounter": session_counter,
        },
    )

    # Update slot and area counters if a numbered slot was assigned
    if slot_id and slot_snapshot:
        slot_ref = repo._slot_ref(slot_id)
        transaction.update(slot_ref, {
            "status": "OCCUPIED",
            "vehicleNumber": vehicle_number,
            "sessionId": session_id,
            "updatedAt": now,
        })
        if area_id and area_snapshot:
            area_ref = repo._area_ref(area_id)
            transaction.update(area_ref, {
                "availableSlots": firestore.Increment(-1),
                "occupiedSlots": firestore.Increment(1),
                "updatedAt": now,
            })
    elif use_corridor and area_id and area_snapshot:
        area_ref = repo._area_ref(area_id)
        transaction.update(area_ref, {
            "corridorAvailable": firestore.Increment(-1),
            "corridorOccupied": firestore.Increment(1),
            "updatedAt": now,
        })

    return session_payload


@firestore.transactional
def _exit_vehicle_txn(
    transaction: firestore.Transaction,
    repo: ParkingRepository,
    vehicle_number: str,
) -> dict:
    vehicle_ref = repo._vehicle_ref(vehicle_number)

    # --- reads ---
    vehicle_snapshot = vehicle_ref.get(transaction=transaction)
    if not vehicle_snapshot.exists:
        raise VehicleNotFoundError(f"Vehicle '{vehicle_number}' has no parking history")
    vehicle = vehicle_snapshot.to_dict()

    active_session_id = vehicle.get("activeSessionId")
    if not active_session_id:
        raise VehicleAlreadyExitedError()

    session_ref = repo._session_ref(active_session_id)
    session_snapshot = session_ref.get(transaction=transaction)
    if not session_snapshot.exists:
        raise VehicleNotFoundError("Active parking session record is missing")

    config_ref = repo._config_ref
    config_snapshot = config_ref.get(transaction=transaction)
    if not config_snapshot.exists:
        raise ParkingConfigMissingError()
    config = config_snapshot.to_dict()

    # --- writes ---
    now = _utcnow()
    transaction.update(session_ref, {"status": "EXITED", "exitTime": now})
    transaction.update(vehicle_ref, {"activeSessionId": None, "updatedAt": now})
    transaction.update(
        config_ref,
        {
            "availableSlots": int(config.get("availableSlots", 0)) + 1,
            "occupiedSlots": max(0, int(config.get("occupiedSlots", 0)) - 1),
        },
    )

    # Release slot / corridor space if one was assigned
    session_data = session_snapshot.to_dict()
    slot_id = session_data.get("slotId")
    area_id = session_data.get("areaId")
    is_corridor = bool(session_data.get("isCorridorParking"))
    if slot_id:
        slot_ref = repo._slot_ref(slot_id)
        transaction.update(slot_ref, {
            "status": "AVAILABLE",
            "vehicleNumber": None,
            "sessionId": None,
            "updatedAt": now,
        })
        if area_id:
            area_ref = repo._area_ref(area_id)
            transaction.update(area_ref, {
                "availableSlots": firestore.Increment(1),
                "occupiedSlots": firestore.Increment(-1),
                "updatedAt": now,
            })
    elif is_corridor and area_id:
        area_ref = repo._area_ref(area_id)
        transaction.update(area_ref, {
            "corridorAvailable": firestore.Increment(1),
            "corridorOccupied": firestore.Increment(-1),
            "updatedAt": now,
        })

    updated_session = session_snapshot.to_dict()
    updated_session.update({"status": "EXITED", "exitTime": now})
    return updated_session


@firestore.transactional
def _reassign_slot_txn(
    transaction: firestore.Transaction,
    repo: ParkingRepository,
    vehicle_number: str,
    new_slot_id: str,
) -> dict:
    """Move a vehicle from its current slot to a new available slot."""
    vehicle_ref = repo._vehicle_ref(vehicle_number)

    # --- reads ---
    vehicle_snapshot = vehicle_ref.get(transaction=transaction)
    if not vehicle_snapshot.exists:
        raise VehicleNotFoundError(f"Vehicle '{vehicle_number}' not found")
    vehicle = vehicle_snapshot.to_dict()

    active_session_id = vehicle.get("activeSessionId")
    if not active_session_id:
        raise VehicleAlreadyExitedError()

    session_ref = repo._session_ref(active_session_id)
    session_snapshot = session_ref.get(transaction=transaction)
    if not session_snapshot.exists:
        raise VehicleNotFoundError("Active parking session record is missing")
    session_data = session_snapshot.to_dict()

    old_slot_id = session_data.get("slotId")
    old_area_id = session_data.get("areaId")
    old_is_corridor = bool(session_data.get("isCorridorParking"))

    # Read new slot
    new_slot_ref = repo._slot_ref(new_slot_id)
    new_slot_snapshot = new_slot_ref.get(transaction=transaction)
    if not new_slot_snapshot.exists:
        raise ParkingSlotNotFoundError()
    new_slot_data = new_slot_snapshot.to_dict()
    if new_slot_data.get("status") != "AVAILABLE":
        raise SlotAlreadyOccupiedError("Selected slot is not available")

    new_area_id = new_slot_data.get("areaId")
    new_slot_number = new_slot_data.get("slotNumber")

    # Read new area for name
    new_area_name = None
    new_area_ref = repo._area_ref(new_area_id)
    new_area_snapshot = new_area_ref.get(transaction=transaction)
    if new_area_snapshot.exists:
        new_area_name = new_area_snapshot.to_dict().get("name")

    # Read old slot and area if they exist
    old_slot_snapshot = None
    old_area_snapshot = None
    old_area_ref = None
    if old_slot_id:
        old_slot_ref = repo._slot_ref(old_slot_id)
        old_slot_snapshot = old_slot_ref.get(transaction=transaction)
    if old_area_id:
        old_area_ref = repo._area_ref(old_area_id)
        # Avoid reading the same area document twice when old == new.
        if old_area_id != new_area_id:
            old_area_snapshot = old_area_ref.get(transaction=transaction)
        else:
            old_area_snapshot = new_area_snapshot
            old_area_ref = new_area_ref

    # --- writes ---
    now = _utcnow()
    same_area = old_area_id == new_area_id

    # Free old slot
    if old_slot_id and old_slot_snapshot and old_slot_snapshot.exists:
        transaction.update(repo._slot_ref(old_slot_id), {
            "status": "AVAILABLE",
            "vehicleNumber": None,
            "sessionId": None,
            "updatedAt": now,
        })

    # Free old corridor space (mutually exclusive with old_slot_id)
    if old_is_corridor and old_area_id and old_area_ref and old_area_snapshot and old_area_snapshot.exists:
        transaction.update(old_area_ref, {
            "corridorAvailable": firestore.Increment(1),
            "corridorOccupied": firestore.Increment(-1),
            "updatedAt": now,
        })

    # Occupy new slot
    transaction.update(new_slot_ref, {
        "status": "OCCUPIED",
        "vehicleNumber": vehicle_number,
        "sessionId": active_session_id,
        "updatedAt": now,
    })

    # Update session
    transaction.update(session_ref, {
        "slotId": new_slot_id,
        "slotNumber": new_slot_number,
        "areaId": new_area_id,
        "areaName": new_area_name,
        "isCorridorParking": False,
    })

    # Update area counters.
    # If the vehicle is just moving slots within the same area, the net area
    # counter change is 0. If the vehicle did not previously have a slot in the
    # old area (e.g., added to an area only), we still need to decrement the new
    # area because it is now physically occupying a slot there.
    if old_slot_id and old_area_id and old_area_ref and old_area_snapshot and old_area_snapshot.exists:
        if not same_area:
            transaction.update(old_area_ref, {
                "availableSlots": firestore.Increment(1),
                "occupiedSlots": firestore.Increment(-1),
                "updatedAt": now,
            })

    if new_area_id and new_area_ref and new_area_snapshot and new_area_snapshot.exists:
        if not (same_area and old_slot_id):
            transaction.update(new_area_ref, {
                "availableSlots": firestore.Increment(-1),
                "occupiedSlots": firestore.Increment(1),
                "updatedAt": now,
            })

    updated_session = session_data.copy()
    updated_session.update({
        "slotId": new_slot_id,
        "slotNumber": new_slot_number,
        "areaId": new_area_id,
        "areaName": new_area_name,
        "isCorridorParking": False,
    })
    return updated_session


@firestore.transactional
def _release_slot_for_pickup_txn(
    transaction: firestore.Transaction,
    repo: ParkingRepository,
    session_id: str,
) -> dict:
    """Free the slot/area occupancy for a session without touching global capacity.

    Called when a valet physically removes the vehicle from its slot
    (``PICKED_UP`` timeline stage) before the vehicle has actually left the
    premises. Global ``parking_config/main`` counters are intentionally
    left untouched here - see ``ParkingRepository.release_slot_for_pickup``.
    """
    session_ref = repo._session_ref(session_id)
    session_snapshot = session_ref.get(transaction=transaction)
    if not session_snapshot.exists:
        raise ParkingSessionNotFoundError(f"Parking session '{session_id}' not found")
    session_data = session_snapshot.to_dict()

    slot_id = session_data.get("slotId")
    area_id = session_data.get("areaId")
    is_corridor = bool(session_data.get("isCorridorParking"))

    if not slot_id and not is_corridor:
        return session_data

    now = _utcnow()

    if slot_id:
        slot_ref = repo._slot_ref(slot_id)
        slot_snapshot = slot_ref.get(transaction=transaction)

        area_ref = repo._area_ref(area_id) if area_id else None
        area_snapshot = area_ref.get(transaction=transaction) if area_ref else None

        if slot_snapshot.exists:
            transaction.update(slot_ref, {
                "status": "AVAILABLE",
                "vehicleNumber": None,
                "sessionId": None,
                "updatedAt": now,
            })

        if area_ref and area_snapshot and area_snapshot.exists:
            transaction.update(area_ref, {
                "availableSlots": firestore.Increment(1),
                "occupiedSlots": firestore.Increment(-1),
                "updatedAt": now,
            })
    elif is_corridor and area_id:
        area_ref = repo._area_ref(area_id)
        area_snapshot = area_ref.get(transaction=transaction)
        if area_snapshot.exists:
            transaction.update(area_ref, {
                "corridorAvailable": firestore.Increment(1),
                "corridorOccupied": firestore.Increment(-1),
                "updatedAt": now,
            })

    transaction.update(session_ref, {
        "slotId": None,
        "slotNumber": None,
        "areaId": None,
        "areaName": None,
        "isCorridorParking": False,
    })

    updated_session = session_data.copy()
    updated_session.update({
        "slotId": None,
        "slotNumber": None,
        "areaId": None,
        "areaName": None,
        "isCorridorParking": False,
    })
    return updated_session
