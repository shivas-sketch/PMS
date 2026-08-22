"""Firebase Admin / Firestore client bootstrap.

The client is created once (lazily, on first use) and reused everywhere via
``get_firestore_client``. Supports three credential modes, resolved in order:

1. ``FIRESTORE_EMULATOR_HOST`` set -> talk to the local Firestore emulator,
   no credentials required. Useful for running this POC without real GCP
   access.
2. ``FIREBASE_CREDENTIALS_PATH`` set -> use that service-account JSON file.
3. Otherwise -> fall back to Application Default Credentials.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache

import firebase_admin
from firebase_admin import credentials, firestore

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_firestore_client():
    """Return a singleton Firestore client, initializing firebase_admin if needed."""
    settings = get_settings()

    if settings.FIRESTORE_EMULATOR_HOST:
        os.environ["FIRESTORE_EMULATOR_HOST"] = settings.FIRESTORE_EMULATOR_HOST

    has_service_account = bool(
        settings.FIREBASE_CREDENTIALS_PATH and os.path.exists(settings.FIREBASE_CREDENTIALS_PATH)
    )

    if settings.FIRESTORE_EMULATOR_HOST and not has_service_account:
        # Passing credential=None to firebase_admin.initialize_app() still
        # falls back to ApplicationDefault() internally, which probes the
        # GCE metadata server and can hang/fail for several seconds when not
        # running on GCP. google-cloud-firestore's own client auto-detects
        # FIRESTORE_EMULATOR_HOST and uses anonymous credentials instead, so
        # talk to it directly rather than going through firebase_admin.
        from google.cloud import firestore as gcf

        logger.info(
            "Initializing Firestore client against emulator at %s (anonymous credentials)",
            settings.FIRESTORE_EMULATOR_HOST,
        )
        return gcf.Client(project=settings.FIREBASE_PROJECT_ID)

    if not firebase_admin._apps:
        if has_service_account:
            cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
            logger.info("Initializing Firebase with service-account credentials")
        else:
            logger.info("Initializing Firebase with Application Default Credentials")
            cred = credentials.ApplicationDefault()

        firebase_admin.initialize_app(cred, {"projectId": settings.FIREBASE_PROJECT_ID})

    return firestore.client()


def reset_firestore_client_cache() -> None:
    """Test helper: clears the cached client (and any firebase_admin apps)."""
    get_firestore_client.cache_clear()
    for app in list(firebase_admin._apps.values()):
        firebase_admin.delete_app(app)
