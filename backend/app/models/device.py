"""Device registry tables for Milestone 2+.

Tables:

- ``devices`` — one row per enrolled device; tied to its owner.
- ``device_credentials`` — token hashes + Keystore alias for each device.
- ``device_health`` — append-only health samples (battery, network, charging).
- ``device_consents`` — per-device capability grants granted by the device
  owner on the device UI. The dashboard never inserts here.
- ``device_activity_events`` — append-only event log pushed by the agent
  (app foreground, screenshot captured, etc.) or the backend (audit chain).
- ``device_installed_apps`` — most-recent inventory snapshot per app.
- ``device_geofences`` — owner-defined geofences for lost-device / family
  alerts.

All identifiers are UUIDs (``gen_random_uuid()``) except ``device_activity_events``
and ``device_installed_apps`` which use ``BIGINT`` because they are
write-heavy and sharded by ``device_id`` for queries.

Enrollment state on ``devices`` is constrained to ``pending``, ``active``,
or ``revoked``. The CHECK constraint exists in the Alembic migration; here
we just rely on the application-layer enum and let the CHECK be the
last-line guard.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow

# Allowed values for free-form text columns. The DB-level CHECK constraints
# in the migration live next to these to keep the source of truth in one
# place — but the Python side uses plain strings so the service layer stays
# dependency-free.
ENROLLMENT_STATES: tuple[str, ...] = ("pending", "active", "revoked")
CAPABILITIES: tuple[str, ...] = (
    "location",
    "screenshot",
    "camera",
    "microphone",
    "screen_share",
    "contacts",
    "calendar",
    "sms",
    "notifications",
    "backup",
)
ACTIVITY_EVENT_TYPES: tuple[str, ...] = (
    "app.foreground",
    "app.installed",
    "app.uninstalled",
    "permission.changed",
    "location.update",
    "screenshot.captured",
    "screen_share.started",
    "screen_share.ended",
    "camera.diagnostic",
    "mic.diagnostic",
    "network.diagnostic",
    "battery.warning",
    "geofence.entered",
    "geofence.exited",
    "tamper.detected",
    "consent.prompted",
    "consent.denied",
)


class Device(Base):
    """A device that has been enrolled by its owner via the AegisOne agent."""

    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        primary_key=True,
        server_default="gen_random_uuid()",
    )

    owner_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Human-friendly display name. Distinct from the hardware model so the
    # operator can rename "Devang's Pixel 8" to "Work phone" if they want.
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    hardware_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    os_version: Mapped[str | None] = mapped_column(String(60), nullable=True)
    app_version: Mapped[str | None] = mapped_column(String(60), nullable=True)

    # Latest snapshot. Updated by ``POST /devices/{id}/heartbeat``.
    battery_pct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    network_type: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # ``pending`` → just enrolled and awaiting first heartbeat (provisional).
    # ``active``  → at least one heartbeat has landed.
    # ``revoked`` → operator disconnected the device; tokens are kept for
    # audit but the agent should refuse to use them.
    enrollment_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # Most queries are "owner's active devices, ordered by last_seen".
        Index("ix_devices_owner_last_seen", "owner_id", "last_seen_at"),
        CheckConstraint(
            "enrollment_state IN ('pending', 'active', 'revoked')",
            name="ck_devices_enrollment_state",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Device id={self.id} name={self.name!r} state={self.enrollment_state!r}>"


class DeviceCredential(Base):
    """Opaque-token hashes for an enrolled device.

    Tokens are issued during ``/devices/enroll/confirm`` and rotated on
    every use. The Keystore alias is the agent's local identifier; the
    server doesn't enforce it, but storing it makes the audit log useful
    when a device is wiped and re-paired.
    """

    __tablename__ = "device_credentials"

    device_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("devices.id", ondelete="CASCADE"),
        primary_key=True,
    )

    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    refresh_token_hash: Mapped[str] = mapped_column(Text, nullable=False, index=True)

    # Android Keystore alias used to wrap the device credential at rest.
    keystore_alias: Mapped[str] = mapped_column(String(120), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DeviceHealth(Base):
    """One row per health sample pushed by the agent."""

    __tablename__ = "device_health"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement="auto")

    device_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    battery_pct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    network_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    is_charging: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    free_storage_mb: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )

    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (Index("ix_device_health_device_recorded", "device_id", "recorded_at"),)


class DeviceConsent(Base):
    """A capability grant issued by the device owner on the device UI.

    The dashboard never inserts here. The agent pushes ``active`` rows
    after the owner taps "Allow" on a consent dialog. Revocations set
    ``revoked_at`` and the row is kept for audit history.
    """

    __tablename__ = "device_consents"

    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        primary_key=True,
        server_default="gen_random_uuid()",
    )

    device_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    capability: Mapped[str] = mapped_column(String(40), nullable=False)

    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_device_consents_device_capability", "device_id", "capability"),
        CheckConstraint(
            "capability IN ('location','screenshot','camera','microphone',"
            "'screen_share','contacts','calendar','sms','notifications','backup')",
            name="ck_device_consents_capability",
        ),
    )


class DeviceActivityEvent(Base):
    """An event emitted by the device or by the backend in response to one.

    Stored on the same connection as the underlying state change so an
    audit row is never lost. ``payload`` is a JSONB bag for event-specific
    extras (e.g. ``{"app": "com.example.app"}`` for ``app.foreground``).
    """

    __tablename__ = "device_activity_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement="auto")

    device_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    event_type: Mapped[str] = mapped_column(String(60), nullable=False)

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_device_activity_device_occurred", "device_id", "occurred_at"),
        Index("ix_device_activity_event_occurred", "event_type", "occurred_at"),
    )


class DeviceInstalledApp(Base):
    """A most-recent inventory snapshot row per (device, package)."""

    __tablename__ = "device_installed_apps"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement="auto")

    device_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
    )

    package_name: Mapped[str] = mapped_column(String(255), nullable=False)
    app_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    version_name: Mapped[str | None] = mapped_column(String(60), nullable=True)
    version_code: Mapped[int | None] = mapped_column(Integer, nullable=True)

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        UniqueConstraint("device_id", "package_name", name="uq_device_app_package"),
        Index("ix_device_apps_device", "device_id"),
    )


class DeviceGeofence(Base):
    """An owner-defined geofence on a device.

    Used by the agent for "entered home" / "exited work" alerts. The
    agent reads these on enrollment and re-evaluates them on every
    location update.
    """

    __tablename__ = "device_geofences"

    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        primary_key=True,
        server_default="gen_random_uuid()",
    )

    device_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(80), nullable=False)
    latitude: Mapped[float] = mapped_column(nullable=False)
    longitude: Mapped[float] = mapped_column(nullable=False)
    radius_meters: Mapped[int] = mapped_column(Integer, nullable=False, default=200)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


# ---- Captures (screenshot / camera / mic) -------------------------------


class DeviceCapture(Base):
    """A captured media blob uploaded by the agent.

    The blob is stored inline as base64 in ``body`` for this slice — the
    dashboard's view layer decodes it for display. For very large blobs
    we swap to MinIO + signed URL later; the schema here already includes
    ``mime_type`` + ``bytes_size`` so the swap is contract-preserving.
    """

    __tablename__ = "device_captures"

    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        primary_key=True,
        server_default="gen_random_uuid()",
    )

    device_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # screenshot | camera | microphone
    mime_type: Mapped[str] = mapped_column(String(80), nullable=False)
    bytes_size: Mapped[int] = mapped_column(Integer, nullable=False)

    body: Mapped[str] = mapped_column(Text, nullable=False)

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        Index("ix_device_captures_device_captured", "device_id", "captured_at"),
        CheckConstraint(
            "kind IN ('screenshot','camera','microphone')",
            name="ck_device_captures_kind",
        ),
    )


# ---- Personal-data snapshots --------------------------------------------


class DevicePersonalSnapshot(Base):
    """The latest snapshot of contacts / calendar / SMS / notifications.

    One row per (device, kind). The agent overwrites this on every push;
    older versions are not retained to keep PII retention tight by
    default. The full audit trail of *access events* still lives in
    ``device_activity_events`` and ``audit_logs``.
    """

    __tablename__ = "device_personal_snapshots"

    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        primary_key=True,
        server_default="gen_random_uuid()",
    )

    device_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
    )

    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    restricted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        UniqueConstraint("device_id", "kind", name="uq_device_personal_kind"),
        CheckConstraint(
            "kind IN ('contacts','calendar','sms','notifications')",
            name="ck_device_personal_kind",
        ),
    )


# ---- Screen-share sessions ----------------------------------------------


class DeviceScreenShareSession(Base):
    """An ongoing screen-share session for a device.

    Created when the dashboard requests ``screen_share``. The agent
    updates ``last_frame_at`` on every frame and the dashboard polls
    / subscribes via WebSocket for live updates. ``expires_at`` is the
    hard cap (default 30 minutes).
    """

    __tablename__ = "device_screen_share_sessions"

    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        primary_key=True,
        server_default="gen_random_uuid()",
    )

    device_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    started_by: Mapped[str] = mapped_column(PGUUID(as_uuid=False), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_frame_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
