"""Device-registry services.

Owns enrollment round-trip, heartbeat ingest, activity ingest, consent
issuance, and command routing. Routers stay thin — they parse requests
and forward here.

Pairing codes are 6 random digits generated at enrollment-request time
and stored as numeric ``pairing_codes`` literal in the enrollment row.
For this slice we encode the code in ``Device`` 's ``name`` field as
``"<display_name>|PAIR:<code>"`` while building; the code is moved off
into a dedicated column during the real persistence refactor. We keep
the code in a side-table for code-only queries: see ``PairingCode``.

The ``PairingCode`` model is intentionally minimal — it expires after
10 minutes and is consumed exactly once.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    hash_refresh_token,
    issue_access_token,
    issue_refresh_token,
)
from app.models import (
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
from app.models.device import CAPABILITIES  # noqa: F401  (re-export)
from app.services import audit


def _now_utc() -> datetime:
    return datetime.now(tz=UTC)


# ---- Pairing-code helper --------------------------------------------------


def _generate_pairing_code() -> str:
    """Return a 6-digit numeric pairing code (avoid leading zeros).

    ``secrets.randbelow(1_000_000)`` returns 0..999999; we zero-pad to six
    chars so the device's UI parser doesn't have to handle variable
    widths.
    """
    return f"{secrets.randbelow(1_000_000):06d}"


def _hash_pairing_code(code: str) -> str:
    """Stable hash so a row can be looked up without storing the raw code.

    We use sha256 (not argon2) because the secret space is only 10^6 —
    argon2's per-call cost would be a poor trade. The raw code is short
    enough to be useless after 10 minutes anyway.
    """
    return hashlib.sha256(code.encode("ascii")).hexdigest()


# ---- Mutable in-memory pairing store --------------------------------------
#
# For Milestone 2 we keep pending pairing codes in-process because they
# expire after 10 minutes and there is no reason to persist them across
# restarts. A multi-process deployment (Milestone 5) will swap this for
# a Redis-backed store with the same interface.
@dataclass
class _PendingPairing:
    owner_id: str
    device_name: str
    expires_at: datetime
    device_id: str
    code_hash: str


_PAIRINGS: dict[str, _PendingPairing] = {}


def _evict_expired_pairings() -> None:
    now = _now_utc()
    expired = [k for k, v in _PAIRINGS.items() if v.expires_at <= now]
    for k in expired:
        _PAIRINGS.pop(k, None)


# ---- Enrollment -----------------------------------------------------------


@dataclass
class EnrollmentRequestResult:
    pairing_code: str
    device_id: str
    expires_at: datetime


async def request_enrollment(
    session: AsyncSession,
    *,
    owner_id: str,
    device_name: str,
    ip: str | None,
    user_agent: str | None,
) -> EnrollmentRequestResult:
    """Generate a 6-digit pairing code and a pre-allocated device id.

    The device row is **not** written until ``confirm_enrollment`` is
    called. We pre-allocate the UUID so the QR code on the dashboard
    can carry it and the agent can submit it back unmodified.
    """
    _evict_expired_pairings()
    code = _generate_pairing_code()
    code_hash = _hash_pairing_code(code)
    device = Device(
        owner_id=owner_id,
        name=device_name,
        enrollment_state="pending",
    )
    session.add(device)
    await session.flush()
    pairing = _PendingPairing(
        owner_id=owner_id,
        device_name=device_name,
        expires_at=_now_utc() + timedelta(minutes=10),
        device_id=device.id,
        code_hash=code_hash,
    )
    _PAIRINGS[code] = pairing
    await audit.record_event(
        session,
        event_type="device.enroll.requested",
        user_id=owner_id,
        ip=ip,
        user_agent=user_agent,
        device_id=device.id,
        metadata={"device_name": device_name},
    )
    await session.commit()
    return EnrollmentRequestResult(
        pairing_code=code,
        device_id=device.id,
        expires_at=pairing.expires_at,
    )


@dataclass
class EnrollmentConfirmResult:
    access_token: str
    refresh_token: str
    access_expires_at: datetime
    device_id: str


async def confirm_enrollment(
    session: AsyncSession,
    *,
    pairing_code: str,
    device_id: str | None,
    public_key_alias: str,
    hardware_model: str | None,
    os_version: str | None,
    app_version: str | None,
    ip: str | None,
    user_agent: str | None,
) -> EnrollmentConfirmResult:
    """Exchange a pairing code for a credential pair.

    Raises ``HTTPException(404)`` if the code is unknown / already used /
    expired. Raises ``HTTPException(409)`` if the caller supplied a
    ``device_id`` and it doesn't match the one reserved for that code.
    """
    _evict_expired_pairings()
    pairing = _PAIRINGS.pop(pairing_code, None)

    if pairing is None or _hash_pairing_code(pairing_code) != pairing.code_hash:
        # Constant-shape response so callers can't probe the code space.
        await audit.record_event(
            session,
            event_type="device.enroll.confirm.failed",
            ip=ip,
            user_agent=user_agent,
            device_id=device_id,
            metadata={"reason": "unknown_or_expired_code"},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "invalid_pairing_code", "message": "Pairing code not found"},
        )

    # If the agent didn't send a device_id (typing-only flow), bind to the
    # reserved one. If it did send one, it MUST match — otherwise it's a
    # security-relevant event we want to see in the audit log.
    if device_id is not None and pairing.device_id != device_id:
        # Keep the pairing valid so the legitimate agent can retry, but
        # log a security-relevant event.
        _PAIRINGS[pairing_code] = pairing
        await audit.record_event(
            session,
            event_type="device.enroll.confirm.mismatch",
            user_id=pairing.owner_id,
            ip=ip,
            user_agent=user_agent,
            device_id=device_id,
            metadata={"expected_device_id": pairing.device_id},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "device_id_mismatch", "message": "Device id mismatch"},
        )

    # Resolve to the canonical device_id reserved at request time.
    device_id = pairing.device_id

    # Activate the device.
    result = await session.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if device is None:  # pragma: no cover - integrity error path
        raise HTTPException(status_code=500, detail="device vanished")

    access, access_exp = issue_access_token(
        user_id=pairing.owner_id, device_id=device_id, scopes=["device"]
    )
    refresh_raw, refresh_digest, refresh_exp = issue_refresh_token()

    device.enrollment_state = "active"
    device.hardware_model = hardware_model
    device.os_version = os_version
    device.app_version = app_version
    device.last_seen_at = _now_utc()
    session.add(
        DeviceCredential(
            device_id=device.id,
            token_hash=hash_refresh_token(access),
            refresh_token_hash=refresh_digest,
            keystore_alias=public_key_alias,
        )
    )
    await audit.record_event(
        session,
        event_type="device.enroll.confirmed",
        user_id=pairing.owner_id,
        ip=ip,
        user_agent=user_agent,
        device_id=device.id,
        metadata={"keystore_alias": public_key_alias},
    )
    await session.commit()
    return EnrollmentConfirmResult(
        access_token=access,
        refresh_token=refresh_raw,
        access_expires_at=access_exp,
        device_id=device.id,
    )


# ---- Listing / detail -----------------------------------------------------


async def list_owner_devices(session: AsyncSession, *, owner_id: str) -> list[Device]:
    result = await session.execute(
        select(Device)
        .where(Device.owner_id == owner_id)
        .order_by(Device.last_seen_at.desc().nulls_last(), Device.created_at.desc())
    )
    return list(result.scalars().all())


async def get_device(session: AsyncSession, *, device_id: str) -> Device | None:
    result = await session.execute(select(Device).where(Device.id == device_id))
    return result.scalar_one_or_none()


async def revoke_device(session: AsyncSession, *, device_id: str) -> None:
    """Mark a device revoked and clear its credentials.

    The device row stays for audit; ``DeviceCredential`` is deleted so
    any old refresh tokens become invalid by lookup.
    """
    now = _now_utc()
    await session.execute(
        update(Device)
        .where(Device.id == device_id)
        .values(enrollment_state="revoked", updated_at=now)
    )
    await session.execute(
        update(DeviceCredential)
        .where(DeviceCredential.device_id == device_id)
        .values(revoked_at=now)
    )
    await audit.record_event(session, event_type="device.revoked", device_id=device_id)
    await session.commit()


# ---- Heartbeat / activity ------------------------------------------------


async def record_heartbeat(
    session: AsyncSession,
    *,
    device_id: str,
    battery_pct: int | None,
    network_type: str | None,
    is_charging: bool | None,
    free_storage_mb: int | None,
    ip: str | None,
    user_agent: str | None,
) -> Device:
    result = await session.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=404, detail={"code": "device_not_found"})

    sample = DeviceHealth(
        device_id=device_id,
        battery_pct=battery_pct,
        network_type=network_type,
        is_charging=bool(is_charging) if is_charging is not None else False,
        free_storage_mb=free_storage_mb,
    )
    session.add(sample)
    device.battery_pct = battery_pct if battery_pct is not None else device.battery_pct
    device.network_type = network_type if network_type is not None else device.network_type
    device.last_seen_at = _now_utc()
    if device.enrollment_state == "pending":
        device.enrollment_state = "active"
    await audit.record_event(
        session,
        event_type="device.heartbeat",
        device_id=device_id,
        ip=ip,
        user_agent=user_agent,
        metadata={"battery_pct": battery_pct, "network_type": network_type},
    )
    await session.commit()
    await session.refresh(device)
    return device


async def ingest_activity(
    session: AsyncSession,
    *,
    device_id: str,
    events: Iterable[dict[str, Any]],
    ip: str | None,
    user_agent: str | None,
) -> int:
    """Insert one row per event. Returns the count.

    The agent may post up to 200 events per request. We keep the call
    cheap by skipping a per-event audit row — the activity row IS the
    audit trail for the agent side.
    """
    n = 0
    for ev in events:
        session.add(
            DeviceActivityEvent(
                device_id=device_id,
                event_type=ev["event_type"],
                payload=ev.get("payload") or {},
            )
        )
        n += 1
    await session.flush()
    await audit.record_event(
        session,
        event_type="device.activity.ingested",
        device_id=device_id,
        ip=ip,
        user_agent=user_agent,
        metadata={"count": n},
    )
    await session.commit()
    return n


async def ingest_apps(
    session: AsyncSession,
    *,
    device_id: str,
    apps: Iterable[dict[str, Any]],
    ip: str | None,
    user_agent: str | None,
) -> int:
    """Upsert the device's installed-app inventory.

    Existing rows get ``last_seen_at`` refreshed; new packages get
    inserted. Packages present in the previous snapshot but missing
    here are left in place with their old ``last_seen_at`` so the
    dashboard can detect "this app used to be installed".
    """
    now = _now_utc()
    n = 0
    for app in apps:
        result = await session.execute(
            select(DeviceInstalledApp).where(
                DeviceInstalledApp.device_id == device_id,
                DeviceInstalledApp.package_name == app["package_name"],
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            session.add(
                DeviceInstalledApp(
                    device_id=device_id,
                    package_name=app["package_name"],
                    app_label=app.get("app_label"),
                    version_name=app.get("version_name"),
                    version_code=app.get("version_code"),
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
        else:
            row.app_label = app.get("app_label") or row.app_label
            row.version_name = app.get("version_name") or row.version_name
            row.version_code = app.get("version_code") or row.version_code
            row.last_seen_at = now
        n += 1
    await audit.record_event(
        session,
        event_type="device.apps.ingested",
        device_id=device_id,
        ip=ip,
        user_agent=user_agent,
        metadata={"count": n},
    )
    await session.commit()
    return n


async def list_activity(
    session: AsyncSession,
    *,
    device_id: str,
    limit: int = 50,
    before_id: int | None = None,
) -> list[DeviceActivityEvent]:
    stmt = (
        select(DeviceActivityEvent)
        .where(DeviceActivityEvent.device_id == device_id)
        .order_by(DeviceActivityEvent.id.desc())
        .limit(limit)
    )
    if before_id is not None:
        stmt = stmt.where(DeviceActivityEvent.id < before_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_apps(session: AsyncSession, *, device_id: str) -> list[DeviceInstalledApp]:
    result = await session.execute(
        select(DeviceInstalledApp)
        .where(DeviceInstalledApp.device_id == device_id)
        .order_by(DeviceInstalledApp.app_label.asc().nulls_last())
    )
    return list(result.scalars().all())


# ---- Consents -------------------------------------------------------------


async def grant_consent(
    session: AsyncSession,
    *,
    device_id: str,
    user_id: str,
    capability: str,
    expires_at: datetime | None,
) -> DeviceConsent:
    if capability not in CAPABILITIES:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_capability", "message": capability},
        )
    row = DeviceConsent(
        device_id=device_id,
        user_id=user_id,
        capability=capability,
        expires_at=expires_at,
    )
    session.add(row)
    await audit.record_event(
        session,
        event_type="device.consent.grant",
        user_id=user_id,
        device_id=device_id,
        metadata={"capability": capability},
    )
    await session.commit()
    await session.refresh(row)
    return row


async def revoke_consent(session: AsyncSession, *, consent_id: str) -> None:
    now = _now_utc()
    await session.execute(
        update(DeviceConsent)
        .where(DeviceConsent.id == consent_id, DeviceConsent.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    await audit.record_event(
        session,
        event_type="device.consent.revoke",
        device_id=None,
        metadata={"consent_id": consent_id},
    )
    await session.commit()


async def list_consents(session: AsyncSession, *, device_id: str) -> list[DeviceConsent]:
    result = await session.execute(
        select(DeviceConsent)
        .where(DeviceConsent.device_id == device_id)
        .order_by(DeviceConsent.granted_at.desc())
    )
    return list(result.scalars().all())


# ---- Commands -------------------------------------------------------------


@dataclass
class CommandRecord:
    id: str
    expires_at: datetime


async def open_command(
    session: AsyncSession,
    *,
    device_id: str,
    capability: str,
    user_id: str,
    session_seconds: int,
    reason: str | None,
    ip: str | None,
    user_agent: str | None,
) -> CommandRecord:
    """Append a command row to the activity stream and audit log.

    For Milestone 2 we don't have a separate ``commands`` table —
    command events land in ``device_activity_events`` and the dashboard
    polls /streams them. The agent also sees them via the activity feed
    (in the Milestone 3 web-socket slice).
    """
    cmd_id = secrets.token_urlsafe(12)
    expires_at = _now_utc() + timedelta(seconds=session_seconds)
    session.add(
        DeviceActivityEvent(
            device_id=device_id,
            event_type=f"command.request.{capability}",
            payload={
                "command_id": cmd_id,
                "session_seconds": session_seconds,
                "expires_at": expires_at.isoformat(),
                "reason": reason or "",
                "requested_by": user_id,
            },
        )
    )
    await audit.record_event(
        session,
        event_type=f"device.command.{capability}",
        user_id=user_id,
        device_id=device_id,
        ip=ip,
        user_agent=user_agent,
        metadata={
            "command_id": cmd_id,
            "session_seconds": session_seconds,
            "reason": reason or "",
        },
    )
    await session.commit()
    return CommandRecord(id=cmd_id, expires_at=expires_at)


# ---- Geofences ------------------------------------------------------------


async def list_geofences(session: AsyncSession, *, device_id: str) -> list[DeviceGeofence]:
    result = await session.execute(
        select(DeviceGeofence)
        .where(DeviceGeofence.device_id == device_id)
        .order_by(DeviceGeofence.created_at.desc())
    )
    return list(result.scalars().all())


async def create_geofence(
    session: AsyncSession,
    *,
    device_id: str,
    name: str,
    latitude: float,
    longitude: float,
    radius_meters: int,
) -> DeviceGeofence:
    fence = DeviceGeofence(
        device_id=device_id,
        name=name,
        latitude=latitude,
        longitude=longitude,
        radius_meters=radius_meters,
    )
    session.add(fence)
    try:
        await session.commit()
    except IntegrityError as err:  # pragma: no cover - defensive
        await session.rollback()
        raise HTTPException(status_code=409, detail={"code": "geofence_conflict"}) from err
    await session.refresh(fence)
    return fence


async def delete_geofence(
    session: AsyncSession,
    *,
    device_id: str,
    fence_id: str,
) -> None:
    fence = await session.get(DeviceGeofence, fence_id)
    if fence is None or fence.device_id != device_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "geofence_not_found", "message": "Geofence not found"},
        )
    await session.delete(fence)
    await session.commit()


# ---- Captures (screenshot / camera / mic) -------------------------------


async def save_capture(
    session: AsyncSession,
    *,
    device_id: str,
    kind: str,
    mime_type: str,
    body_b64: str,
) -> DeviceCapture:
    if kind not in {"screenshot", "camera", "microphone"}:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_capture_kind", "message": kind},
        )
    raw = body_b64.encode("ascii")
    row = DeviceCapture(
        device_id=device_id,
        kind=kind,
        mime_type=mime_type,
        bytes_size=len(raw),
        body=body_b64,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def list_captures(
    session: AsyncSession,
    *,
    device_id: str,
    kind: str | None = None,
    limit: int = 20,
) -> list[DeviceCapture]:
    stmt = select(DeviceCapture).where(DeviceCapture.device_id == device_id)
    if kind is not None:
        stmt = stmt.where(DeviceCapture.kind == kind)
    stmt = stmt.order_by(DeviceCapture.captured_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ---- Personal snapshots (contacts / calendar / sms / notifications) -----


async def save_personal_snapshot(
    session: AsyncSession,
    *,
    device_id: str,
    kind: str,
    payload: dict[str, Any],
    restricted: bool = False,
) -> DevicePersonalSnapshot:
    if kind not in {"contacts", "calendar", "sms", "notifications"}:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_personal_kind", "message": kind},
        )
    # Upsert by (device_id, kind). One row per device per kind, replaced
    # on every push so PII retention stays tight.
    existing = await session.execute(
        select(DevicePersonalSnapshot).where(
            DevicePersonalSnapshot.device_id == device_id,
            DevicePersonalSnapshot.kind == kind,
        )
    )
    row = existing.scalar_one_or_none()
    if row is None:
        row = DevicePersonalSnapshot(
            device_id=device_id,
            kind=kind,
            payload=payload,
            restricted=restricted,
        )
        session.add(row)
    else:
        row.payload = payload
        row.restricted = restricted
    await session.commit()
    await session.refresh(row)
    return row


async def get_personal_snapshot(
    session: AsyncSession,
    *,
    device_id: str,
    kind: str,
) -> DevicePersonalSnapshot | None:
    result = await session.execute(
        select(DevicePersonalSnapshot).where(
            DevicePersonalSnapshot.device_id == device_id,
            DevicePersonalSnapshot.kind == kind,
        )
    )
    return result.scalar_one_or_none()


# ---- Screen-share sessions ----------------------------------------------


async def open_screen_share(
    session: AsyncSession,
    *,
    device_id: str,
    started_by: str,
    session_seconds: int,
) -> DeviceScreenShareSession:
    now = _now_utc()
    expires_at = now + timedelta(seconds=min(session_seconds, 1800))
    row = DeviceScreenShareSession(
        device_id=device_id,
        started_by=started_by,
        started_at=now,
        expires_at=expires_at,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def touch_screen_share(
    session: AsyncSession,
    *,
    session_id: str,
) -> DeviceScreenShareSession | None:
    row = await session.get(DeviceScreenShareSession, session_id)
    if row is None or row.ended_at is not None:
        return row
    row.last_frame_at = _now_utc()
    await session.commit()
    await session.refresh(row)
    return row


async def end_screen_share(
    session: AsyncSession,
    *,
    session_id: str,
    reason: str | None = None,
) -> DeviceScreenShareSession | None:
    row = await session.get(DeviceScreenShareSession, session_id)
    if row is None:
        return None
    if row.ended_at is not None:
        return row
    row.ended_at = _now_utc()
    row.end_reason = reason or "completed"
    await session.commit()
    await session.refresh(row)
    return row


async def latest_screen_share(
    session: AsyncSession,
    *,
    device_id: str,
) -> DeviceScreenShareSession | None:
    """Return the live screen-share session for a device, if any."""
    result = await session.execute(
        select(DeviceScreenShareSession)
        .where(
            DeviceScreenShareSession.device_id == device_id,
            DeviceScreenShareSession.ended_at.is_(None),
        )
        .order_by(DeviceScreenShareSession.started_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
