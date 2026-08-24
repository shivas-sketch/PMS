"""Capacity alert service.

Monitors parking occupancy and fires alerts when thresholds are crossed:
50%, 80%, 90%, 95%, 98%, 100%.

Notifications are stored in Firestore (``parking_alerts`` collection) so the
frontend can poll and display them.  Threshold deduplication is tracked in
``parking_config/main`` under ``triggeredThresholds`` — a threshold fires
only once on the way up and resets when occupancy drops below it so it can
fire again on the next fill cycle.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from google.cloud import firestore

from app.repositories.parking_repository import ParkingRepository

logger = logging.getLogger(__name__)

ALERT_THRESHOLDS = [50, 80, 90, 95, 98, 100]
ALERTS_COLLECTION = "parking_alerts"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AlertService:
    def __init__(self, repository: ParkingRepository):
        self.repository = repository

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def check_capacity(self) -> Optional[dict]:
        """Check current occupancy and fire alerts if thresholds are crossed.

        Called after every vehicle entry or exit.  Returns the alert dict
        if one was fired, otherwise ``None``.
        """
        config = self.repository.get_capacity()
        total = int(config.get("totalCapacity", 0))
        occupied = int(config.get("occupiedSlots", 0))

        if total <= 0:
            return None

        pct = round((occupied / total) * 100, 1)
        triggered: Dict[str, bool] = config.get("triggeredThresholds", {})

        # --- reset thresholds that are no longer met ---
        for t in ALERT_THRESHOLDS:
            key = str(t)
            if triggered.get(key) and pct < t:
                triggered[key] = False
                logger.info("alert_threshold_reset threshold=%s pct=%.1f", t, pct)

        # --- fire newly-crossed thresholds ---
        fired_alert: Optional[dict] = None
        for t in ALERT_THRESHOLDS:
            key = str(t)
            if pct >= t and not triggered.get(key):
                triggered[key] = True
                alert = self._create_alert(t, occupied, total, pct)
                fired_alert = alert
                logger.warning(
                    "alert_threshold_fired threshold=%s pct=%.1f occupied=%d total=%d",
                    t, pct, occupied, total,
                )

        # --- persist updated trigger state ---
        self.repository._config_ref.update({"triggeredThresholds": triggered})

        return fired_alert

    def list_alerts(self, limit: int = 50) -> List[dict]:
        """Return recent alerts, newest first."""
        db = self.repository.db
        docs = list(
            db.collection(ALERTS_COLLECTION)
            .order_by("createdAt", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .stream()
        )
        return [doc.to_dict() for doc in docs]

    def mark_alert_read(self, alert_id: str) -> None:
        db = self.repository.db
        db.collection(ALERTS_COLLECTION).document(alert_id).update(
            {"read": True, "readAt": _utcnow()}
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _create_alert(self, threshold: int, occupied: int, total: int, pct: float) -> dict:
        severity = self._severity_for(threshold)
        message = self._message_for(threshold, occupied, total, pct)
        now = _utcnow()

        alert_payload = {
            "threshold": threshold,
            "occupiedSlots": occupied,
            "totalCapacity": total,
            "occupancyPercent": pct,
            "severity": severity,
            "message": message,
            "read": False,
            "createdAt": now,
        }

        db = self.repository.db
        doc_ref = db.collection(ALERTS_COLLECTION).document()
        alert_payload["alertId"] = doc_ref.id
        doc_ref.set(alert_payload)

        return alert_payload

    @staticmethod
    def _severity_for(threshold: int) -> str:
        if threshold >= 98:
            return "CRITICAL"
        if threshold >= 90:
            return "HIGH"
        if threshold >= 80:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _message_for(threshold: int, occupied: int, total: int, pct: float) -> str:
        if threshold == 100:
            return f"Parking is FULL — {occupied}/{total} slots occupied ({pct}%)."
        return (
            f"Parking {pct}% full — {occupied}/{total} slots occupied "
            f"(crossed {threshold}% threshold)."
        )
