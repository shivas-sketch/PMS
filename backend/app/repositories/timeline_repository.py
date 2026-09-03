"""Firestore-backed persistence for parking session timeline (valet journey) events.

Collection
----------
``parking_sessions/{sessionId}/timeline_events/{eventId}``
    One immutable document per history event. Events are never updated or
    deleted - the same stage may be recorded multiple times (e.g. a vehicle
    can be re-assigned for parking after a failed attempt). ``currentStage``
    on the parent ``parking_sessions/{sessionId}`` document is kept in sync
    with the most recently created event as a fast-read convenience field.

All timestamps are generated server-side (``_utcnow()``); client-supplied
timestamps are never trusted or accepted.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from google.cloud import firestore

from app.enums import ParkingTimelineStage, get_stage_display_name
from app.exceptions import ParkingSessionNotFoundError

SESSIONS_COLLECTION = "parking_sessions"
TIMELINE_SUBCOLLECTION = "timeline_events"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _stage_value(stage: "ParkingTimelineStage | str") -> str:
    return stage.value if isinstance(stage, ParkingTimelineStage) else stage


class TimelineRepository:
    def __init__(self, db: firestore.Client):
        self.db = db

    # --- references -------------------------------------------------
    def _session_ref(self, session_id: str):
        return self.db.collection(SESSIONS_COLLECTION).document(session_id)

    def _timeline_ref(self, session_id: str):
        return self._session_ref(session_id).collection(TIMELINE_SUBCOLLECTION)

    # --- reads --------------------------------------------------------
    def get_session_timeline(self, session_id: str) -> List[dict]:
        """Full history for a session, sorted oldest -> newest."""
        docs = self._timeline_ref(session_id).order_by("timestamp").stream()
        return [doc.to_dict() for doc in docs]

    # --- writes ---------------------------------------------------------
    def create_timeline_event(
        self,
        session_id: str,
        vehicle_number: str,
        stage: "ParkingTimelineStage | str",
        area_id: Optional[str] = None,
        area_name: Optional[str] = None,
        slot_id: Optional[str] = None,
        slot_number: Optional[str] = None,
        valet_id: Optional[str] = None,
        valet_name: Optional[str] = None,
        notes: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> dict:
        """Append a new immutable timeline event and sync ``currentStage``.

        Never overwrites or deletes prior events - always creates a brand
        new document with a fresh auto-generated ID and a server timestamp.
        """
        transaction = self.db.transaction()
        return _create_timeline_event_txn(
            transaction,
            self,
            session_id=session_id,
            vehicle_number=vehicle_number,
            stage=stage,
            area_id=area_id,
            area_name=area_name,
            slot_id=slot_id,
            slot_number=slot_number,
            valet_id=valet_id,
            valet_name=valet_name,
            notes=notes,
            metadata=metadata,
        )

    def update_current_stage(self, session_id: str, stage: "ParkingTimelineStage | str") -> None:
        """Directly sync ``currentStage`` without creating a timeline event.

        Exposed for callers that manage event creation separately but still
        need to keep the session's fast-read stage field current.
        """
        self._session_ref(session_id).update(
            {"currentStage": _stage_value(stage), "updatedAt": _utcnow()}
        )


@firestore.transactional
def _create_timeline_event_txn(
    transaction: firestore.Transaction,
    repo: TimelineRepository,
    session_id: str,
    vehicle_number: str,
    stage: "ParkingTimelineStage | str",
    area_id: Optional[str],
    area_name: Optional[str],
    slot_id: Optional[str],
    slot_number: Optional[str],
    valet_id: Optional[str],
    valet_name: Optional[str],
    notes: Optional[str],
    metadata: Optional[Dict[str, Any]],
) -> dict:
    session_ref = repo._session_ref(session_id)
    session_snapshot = session_ref.get(transaction=transaction)
    if not session_snapshot.exists:
        raise ParkingSessionNotFoundError(f"Parking session '{session_id}' not found")

    stage_value = _stage_value(stage)
    event_ref = repo._timeline_ref(session_id).document()
    now = _utcnow()

    event_payload = {
        "eventId": event_ref.id,
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

    transaction.set(event_ref, event_payload)
    session_update: Dict[str, Any] = {"currentStage": stage_value, "updatedAt": now}
    # Preserve the last known valet assignment unless this event explicitly
    # carries a new one - not every workflow action re-sends valet identity.
    if valet_id is not None or valet_name is not None:
        session_update["currentValetId"] = valet_id
        session_update["currentValetName"] = valet_name
    transaction.update(session_ref, session_update)

    return event_payload
