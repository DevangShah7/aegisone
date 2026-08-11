"""ORM models for AegisOne.

Each module defines one table. They are all re-exported here so
``from app.models import Base`` (and Alembic's ``target_metadata``) sees
the complete schema in one place.

Tables in Milestone 1:

- ``User`` — accounts; ``email`` is CITEXT (case-insensitive unique).
- ``Session`` — one row per active refresh token; rotated/revoked chain.
- ``AuditLog`` — append-only event log; ``BIGSERIAL`` for write volume.
- ``Consent`` — user agreements to documents (ToS, privacy, enrollment).

Tables in Milestone 2:

- ``Device`` — one row per enrolled device.
- ``DeviceCredential`` — opaque-token hashes + Keystore alias.
- ``DeviceHealth`` — append-only health samples.
- ``DeviceConsent`` — per-device capability grants made on the device.
- ``DeviceActivityEvent`` — append-only agent event stream.
- ``DeviceInstalledApp`` — inventory snapshot rows.
- ``DeviceGeofence`` — owner-defined geofences.
"""

from __future__ import annotations

from app.db.base import Base
from app.models.audit_log import AuditLog
from app.models.consent import Consent
from app.models.device import (
    ACTIVITY_EVENT_TYPES,
    CAPABILITIES,
    ENROLLMENT_STATES,
    Device,
    DeviceActivityEvent,
    DeviceCapture,
    DeviceConsent,
    DeviceCredential,
    DeviceGeofence,
    DeviceHealth,
    DeviceInstalledApp,
    DevicePersonalSnapshot,
    DeviceScreenShareSession,
)
from app.models.session import Session
from app.models.user import User

__all__ = [
    "ACTIVITY_EVENT_TYPES",
    "CAPABILITIES",
    "ENROLLMENT_STATES",
    "AuditLog",
    "Base",
    "Consent",
    "Device",
    "DeviceActivityEvent",
    "DeviceCapture",
    "DeviceConsent",
    "DeviceCredential",
    "DeviceGeofence",
    "DeviceHealth",
    "DeviceInstalledApp",
    "DevicePersonalSnapshot",
    "DeviceScreenShareSession",
    "Session",
    "User",
]
