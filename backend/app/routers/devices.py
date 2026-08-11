"""Device-registry endpoints.

Routes
------

- ``GET    /devices``                              — list owner's devices.
- ``POST   /devices/enroll/request``               — owner generates a pairing code.
- ``POST   /devices/enroll/confirm``               — agent exchanges pairing code → tokens.
- ``GET    /devices/{id}``                         — single device + consents + last activity.
- ``DELETE /devices/{id}``                         — revoke device.
- ``POST   /devices/{id}/heartbeat``               — health sample.
- ``POST   /devices/{id}/activity``                — batched activity events.
- ``POST   /devices/{id}/apps``                    — installed-app snapshot.
- ``GET    /devices/{id}/activity``                — paginated activity stream.
- ``GET    /devices/{id}/apps``                    — read installed-app list.
- ``POST   /devices/{id}/consents``                — owner grants a capability (device-pushed).
- ``GET    /devices/{id}/consents``                — list active consents.
- ``POST   /devices/{id}/command/{capability}``    — dashboard-initiated command.

Command ``capability`` is one of ``screenshot``, ``screen_share``, ``locate``,
``lock``, ``ring``. Sensitive commands consult ``services.permissions``
before they are persisted; if no active consent exists the response is
a 403 with ``code=consent_required`` so the dashboard can show
"Awaiting device owner approval".
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.schemas.device import (
    CalendarSnapshotIn,
    CalendarSnapshotOut,
    CaptureOut,
    CommandIn,
    CommandOut,
    ContactsSnapshotIn,
    ContactsSnapshotOut,
    DeviceActivityBatchIn,
    DeviceActivityEventOut,
    DeviceConsentIn,
    DeviceConsentOut,
    DeviceDetailOut,
    DeviceHeartbeatIn,
    DeviceOut,
    EnrollConfirmIn,
    EnrollConfirmOut,
    EnrollRequestIn,
    EnrollRequestOut,
    GeofenceIn,
    GeofenceOut,
    InstalledAppsBatchIn,
    NotificationSnapshotIn,
    NotificationSnapshotOut,
    SmsSnapshotIn,
    SmsSnapshotOut,
)
from app.services import audit
from app.services import devices as device_service
from app.services.permissions import (
    ConsentDecision,
    check_capability,
    is_valid_capability,
)

router = APIRouter()


def _client_ip(request: Request) -> str | None:
    if request.client is None:
        return None
    import ipaddress

    candidate = request.client.host
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return None
    return candidate


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


def _iso(dt: datetime | None) -> str:
    return dt.isoformat() if dt else ""


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _device_out(d) -> DeviceOut:
    return DeviceOut(
        id=d.id,
        owner_id=d.owner_id,
        name=d.name,
        hardware_model=d.hardware_model,
        os_version=d.os_version,
        app_version=d.app_version,
        battery_pct=d.battery_pct,
        network_type=d.network_type,
        enrollment_state=d.enrollment_state,
        created_at=_iso(d.created_at),
        last_seen_at=_iso(d.last_seen_at),
    )


async def _ensure_owner(session: AsyncSession, *, device_id: str, owner_id: str):
    device = await device_service.get_device(session, device_id=device_id)
    if device is None or device.owner_id != owner_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "device_not_found", "message": "Device not found"},
        )
    return device


# ---- Owner-side enrollment -----------------------------------------------


@router.post(
    "/enroll/request",
    status_code=status.HTTP_201_CREATED,
    summary="Generate a pairing code for a new device",
    response_model=EnrollRequestOut,
)
async def enroll_request(
    payload: EnrollRequestIn,
    request: Request,
    session: AsyncSession = Depends(get_db),
    claims: dict = Depends(get_current_user),
) -> EnrollRequestOut:
    result = await device_service.request_enrollment(
        session,
        owner_id=claims["sub"],
        device_name=payload.device_name,
        ip=_client_ip(request),
        user_agent=_user_agent(request),
    )
    return EnrollRequestOut(
        pairing_code=result.pairing_code,
        device_id=result.device_id,
        expires_at=result.expires_at.isoformat(),
    )


# ---- Agent-side enrollment confirmation ----------------------------------


@router.post(
    "/enroll/confirm",
    status_code=status.HTTP_200_OK,
    summary="Exchange a pairing code for an access/refresh token pair",
    response_model=EnrollConfirmOut,
)
async def enroll_confirm(
    payload: EnrollConfirmIn,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> EnrollConfirmOut:
    result = await device_service.confirm_enrollment(
        session,
        pairing_code=payload.pairing_code,
        device_id=payload.device_id,
        public_key_alias=payload.public_key_alias,
        hardware_model=payload.hardware_model,
        os_version=payload.os_version,
        app_version=payload.app_version,
        ip=_client_ip(request),
        user_agent=_user_agent(request),
    )
    expires_in = max(
        0,
        int((result.access_expires_at - datetime.now(tz=UTC)).total_seconds()),
    )
    return EnrollConfirmOut(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        expires_in=expires_in,
        device_id=result.device_id,
    )


# ---- List / detail --------------------------------------------------------


@router.get(
    "",
    summary="List the caller's enrolled devices",
    response_model=list[DeviceOut],
)
async def list_devices(
    session: AsyncSession = Depends(get_db),
    claims: dict = Depends(get_current_user),
) -> list[DeviceOut]:
    rows = await device_service.list_owner_devices(session, owner_id=claims["sub"])
    return [_device_out(r) for r in rows]


@router.get(
    "/{device_id}",
    summary="Fetch a single device with consents and recent activity",
    response_model=DeviceDetailOut,
)
async def get_device(
    device_id: str = Path(..., min_length=36, max_length=36),
    session: AsyncSession = Depends(get_db),
    claims: dict = Depends(get_current_user),
) -> DeviceDetailOut:
    device = await _ensure_owner(session, device_id=device_id, owner_id=claims["sub"])
    consents = await device_service.list_consents(session, device_id=device.id)
    last_activity = await device_service.list_activity(session, device_id=device.id, limit=20)
    return DeviceDetailOut(
        **_device_out(device).model_dump(),
        consents=[
            DeviceConsentOut(
                id=c.id,
                capability=c.capability,
                granted_at=_iso(c.granted_at),
                expires_at=_iso(c.expires_at),
                revoked_at=_iso(c.revoked_at),
            )
            for c in consents
        ],
        last_activity=[
            DeviceActivityEventOut(
                id=e.id,
                device_id=e.device_id,
                event_type=e.event_type,
                occurred_at=_iso(e.occurred_at),
                payload=e.payload,
            )
            for e in last_activity
        ],
    )


@router.delete(
    "/{device_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Revoke a device",
)
async def revoke_device(
    device_id: str = Path(..., min_length=36, max_length=36),
    session: AsyncSession = Depends(get_db),
    claims: dict = Depends(get_current_user),
) -> Response:
    await _ensure_owner(session, device_id=device_id, owner_id=claims["sub"])
    await device_service.revoke_device(session, device_id=device_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- Agent-side ingest ----------------------------------------------------


@router.post(
    "/{device_id}/heartbeat",
    summary="Push a health sample (agent-only)",
    response_model=DeviceOut,
)
async def heartbeat(
    payload: DeviceHeartbeatIn,
    request: Request,
    device_id: str = Path(..., min_length=36, max_length=36),
    session: AsyncSession = Depends(get_db),
    claims: dict = Depends(get_current_user),
) -> DeviceOut:
    await _ensure_owner(session, device_id=device_id, owner_id=claims["sub"])
    device = await device_service.record_heartbeat(
        session,
        device_id=device_id,
        battery_pct=payload.battery_pct,
        network_type=payload.network_type,
        is_charging=payload.is_charging,
        free_storage_mb=payload.free_storage_mb,
        ip=_client_ip(request),
        user_agent=_user_agent(request),
    )
    return _device_out(device)


@router.post(
    "/{device_id}/activity",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Push a batch of activity events (agent-only)",
)
async def push_activity(
    payload: DeviceActivityBatchIn,
    request: Request,
    device_id: str = Path(..., min_length=36, max_length=36),
    session: AsyncSession = Depends(get_db),
    claims: dict = Depends(get_current_user),
) -> dict[str, int]:
    await _ensure_owner(session, device_id=device_id, owner_id=claims["sub"])
    n = await device_service.ingest_activity(
        session,
        device_id=device_id,
        events=[e.model_dump() for e in payload.events],
        ip=_client_ip(request),
        user_agent=_user_agent(request),
    )
    return {"accepted": n}


@router.post(
    "/{device_id}/apps",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Push installed-app inventory snapshot (agent-only)",
)
async def push_apps(
    payload: InstalledAppsBatchIn,
    request: Request,
    device_id: str = Path(..., min_length=36, max_length=36),
    session: AsyncSession = Depends(get_db),
    claims: dict = Depends(get_current_user),
) -> dict[str, int]:
    await _ensure_owner(session, device_id=device_id, owner_id=claims["sub"])
    n = await device_service.ingest_apps(
        session,
        device_id=device_id,
        apps=[a.model_dump() for a in payload.apps],
        ip=_client_ip(request),
        user_agent=_user_agent(request),
    )
    return {"accepted": n}


@router.get(
    "/{device_id}/activity",
    summary="Read recent activity for a device (owner-only)",
    response_model=list[DeviceActivityEventOut],
)
async def list_activity(
    device_id: str = Path(..., min_length=36, max_length=36),
    limit: int = Query(default=50, ge=1, le=200),
    before_id: int | None = Query(default=None, ge=0),
    session: AsyncSession = Depends(get_db),
    claims: dict = Depends(get_current_user),
) -> list[DeviceActivityEventOut]:
    await _ensure_owner(session, device_id=device_id, owner_id=claims["sub"])
    rows = await device_service.list_activity(
        session, device_id=device_id, limit=limit, before_id=before_id
    )
    return [
        DeviceActivityEventOut(
            id=e.id,
            device_id=e.device_id,
            event_type=e.event_type,
            occurred_at=_iso(e.occurred_at),
            payload=e.payload,
        )
        for e in rows
    ]


@router.get(
    "/{device_id}/apps",
    summary="Read installed-app inventory (owner-only)",
)
async def list_apps(
    device_id: str = Path(..., min_length=36, max_length=36),
    session: AsyncSession = Depends(get_db),
    claims: dict = Depends(get_current_user),
):
    await _ensure_owner(session, device_id=device_id, owner_id=claims["sub"])
    rows = await device_service.list_apps(session, device_id=device_id)
    return {
        "device_id": device_id,
        "apps": [
            {
                "package_name": r.package_name,
                "app_label": r.app_label,
                "version_name": r.version_name,
                "version_code": r.version_code,
                "first_seen_at": _iso(r.first_seen_at),
                "last_seen_at": _iso(r.last_seen_at),
            }
            for r in rows
        ],
    }


# ---- Consents -------------------------------------------------------------


@router.post(
    "/{device_id}/consents",
    status_code=status.HTTP_201_CREATED,
    summary="Grant a capability (device-only — pushed by the agent)",
    response_model=DeviceConsentOut,
)
async def grant_consent(
    payload: DeviceConsentIn,
    device_id: str = Path(..., min_length=36, max_length=36),
    session: AsyncSession = Depends(get_db),
    claims: dict = Depends(get_current_user),
) -> DeviceConsentOut:
    if not is_valid_capability(payload.capability):
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_capability", "message": payload.capability},
        )
    await _ensure_owner(session, device_id=device_id, owner_id=claims["sub"])
    expires_at = None
    if payload.expires_at:
        expires_at = datetime.fromisoformat(payload.expires_at.replace("Z", "+00:00"))
    row = await device_service.grant_consent(
        session,
        device_id=device_id,
        user_id=claims["sub"],
        capability=payload.capability,
        expires_at=expires_at,
    )
    return DeviceConsentOut(
        id=row.id,
        capability=row.capability,
        granted_at=_iso(row.granted_at),
        expires_at=_iso(row.expires_at),
        revoked_at=_iso(row.revoked_at),
    )


@router.get(
    "/{device_id}/consents",
    summary="List all consents granted on the device (owner-only)",
    response_model=list[DeviceConsentOut],
)
async def list_consents(
    device_id: str = Path(..., min_length=36, max_length=36),
    session: AsyncSession = Depends(get_db),
    claims: dict = Depends(get_current_user),
) -> list[DeviceConsentOut]:
    await _ensure_owner(session, device_id=device_id, owner_id=claims["sub"])
    rows = await device_service.list_consents(session, device_id=device_id)
    return [
        DeviceConsentOut(
            id=r.id,
            capability=r.capability,
            granted_at=_iso(r.granted_at),
            expires_at=_iso(r.expires_at),
            revoked_at=_iso(r.revoked_at),
        )
        for r in rows
    ]


# ---- Captures (screenshot / camera / mic) --------------------------------


@router.post(
    "/{device_id}/captures",
    status_code=status.HTTP_201_CREATED,
    summary="Upload a captured media blob (agent-only)",
)
async def upload_capture(
    request: Request,
    device_id: str = Path(..., min_length=36, max_length=36),
    session: AsyncSession = Depends(get_db),
    claims: dict = Depends(get_current_user),
):
    await _ensure_owner(session, device_id=device_id, owner_id=claims["sub"])
    body = await request.json()
    kind = body.get("kind")
    mime_type = body.get("mime_type")
    body_b64 = body.get("body_b64")
    if not isinstance(kind, str) or not isinstance(mime_type, str) or not isinstance(body_b64, str):
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_capture_payload"},
        )
    row = await device_service.save_capture(
        session,
        device_id=device_id,
        kind=kind,
        mime_type=mime_type,
        body_b64=body_b64,
    )
    await audit.record_event(
        session,
        event_type=f"device.capture.{kind}",
        user_id=claims["sub"],
        device_id=device_id,
        ip=_client_ip(request),
        user_agent=_user_agent(request),
        metadata={"capture_id": row.id, "bytes": row.bytes_size},
    )
    await session.commit()
    return {"id": row.id, "kind": row.kind, "captured_at": _iso(row.captured_at)}


@router.get(
    "/{device_id}/captures",
    summary="List recent captures (owner-only)",
    response_model=list[CaptureOut],
)
async def list_captures(
    device_id: str = Path(..., min_length=36, max_length=36),
    kind: str | None = Query(default=None, max_length=20),
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    claims: dict = Depends(get_current_user),
) -> list[CaptureOut]:
    await _ensure_owner(session, device_id=device_id, owner_id=claims["sub"])
    rows = await device_service.list_captures(session, device_id=device_id, kind=kind, limit=limit)
    return [
        CaptureOut(
            id=r.id,
            kind=r.kind,
            captured_at=_iso(r.captured_at),
            mime_type=r.mime_type,
            bytes_size=r.bytes_size,
            body_b64=r.body,
        )
        for r in rows
    ]


@router.get(
    "/{device_id}/captures/{capture_id}",
    summary="Fetch a single capture (owner-only)",
    response_model=CaptureOut,
)
async def get_capture(
    device_id: str = Path(..., min_length=36, max_length=36),
    capture_id: str = Path(..., min_length=36, max_length=36),
    session: AsyncSession = Depends(get_db),
    claims: dict = Depends(get_current_user),
) -> CaptureOut:
    await _ensure_owner(session, device_id=device_id, owner_id=claims["sub"])
    rows = await device_service.list_captures(session, device_id=device_id, limit=200)
    for r in rows:
        if str(r.id) == capture_id:
            return CaptureOut(
                id=r.id,
                kind=r.kind,
                captured_at=_iso(r.captured_at),
                mime_type=r.mime_type,
                bytes_size=r.bytes_size,
                body_b64=r.body,
            )
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "capture_not_found", "message": "Capture not found"},
    )


# ---- Personal-data snapshots ---------------------------------------------


_PERSONAL_KINDS = {"contacts", "calendar", "sms", "notifications"}


async def _upsert_personal(
    *,
    device_id: str,
    user_id: str,
    kind: str,
    items: list[dict],
    request: Request,
    session: AsyncSession,
    restricted: bool = False,
) -> dict[str, Any]:
    row = await device_service.save_personal_snapshot(
        session,
        device_id=device_id,
        kind=kind,
        payload={"items": items},
        restricted=restricted,
    )
    await audit.record_event(
        session,
        event_type=f"device.personal.{kind}",
        user_id=user_id,
        device_id=device_id,
        ip=_client_ip(request),
        user_agent=_user_agent(request),
        metadata={"count": len(items), "restricted": restricted},
    )
    await session.commit()
    return {"device_id": device_id, "kind": kind, "updated_at": _iso(row.updated_at), "count": len(items)}


@router.post(
    "/{device_id}/personal/contacts",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Push contacts snapshot (agent-only)",
    response_model=ContactsSnapshotOut,
)
async def push_contacts(
    payload: ContactsSnapshotIn,
    request: Request,
    device_id: str = Path(..., min_length=36, max_length=36),
    session: AsyncSession = Depends(get_db),
    claims: dict = Depends(get_current_user),
) -> ContactsSnapshotOut:
    await _ensure_owner(session, device_id=device_id, owner_id=claims["sub"])
    out = await _upsert_personal(
        device_id=device_id,
        user_id=claims["sub"],
        kind="contacts",
        items=payload.contacts,
        request=request,
        session=session,
    )
    return ContactsSnapshotOut(
        device_id=device_id,
        contacts=payload.contacts,
        updated_at=str(out["updated_at"]),
    )


@router.post(
    "/{device_id}/personal/calendar",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Push calendar snapshot (agent-only)",
    response_model=CalendarSnapshotOut,
)
async def push_calendar(
    payload: CalendarSnapshotIn,
    request: Request,
    device_id: str = Path(..., min_length=36, max_length=36),
    session: AsyncSession = Depends(get_db),
    claims: dict = Depends(get_current_user),
) -> CalendarSnapshotOut:
    await _ensure_owner(session, device_id=device_id, owner_id=claims["sub"])
    await _upsert_personal(
        device_id=device_id,
        user_id=claims["sub"],
        kind="calendar",
        items=payload.events,
        request=request,
        session=session,
    )
    return CalendarSnapshotOut(
        device_id=device_id,
        events=payload.events,
        updated_at=_iso(_now()),
    )


@router.post(
    "/{device_id}/personal/sms",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Push SMS snapshot (agent-only, restricted on Android 13+)",
    response_model=SmsSnapshotOut,
)
async def push_sms(
    payload: SmsSnapshotIn,
    request: Request,
    device_id: str = Path(..., min_length=36, max_length=36),
    restricted: bool = Query(default=False),
    session: AsyncSession = Depends(get_db),
    claims: dict = Depends(get_current_user),
) -> SmsSnapshotOut:
    await _ensure_owner(session, device_id=device_id, owner_id=claims["sub"])
    await _upsert_personal(
        device_id=device_id,
        user_id=claims["sub"],
        kind="sms",
        items=payload.messages,
        request=request,
        session=session,
        restricted=restricted,
    )
    return SmsSnapshotOut(
        device_id=device_id,
        messages=payload.messages,
        updated_at=_iso(_now()),
        restricted=restricted,
    )


@router.post(
    "/{device_id}/personal/notifications",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Push notifications snapshot (agent-only)",
    response_model=NotificationSnapshotOut,
)
async def push_notifications(
    payload: NotificationSnapshotIn,
    request: Request,
    device_id: str = Path(..., min_length=36, max_length=36),
    session: AsyncSession = Depends(get_db),
    claims: dict = Depends(get_current_user),
) -> NotificationSnapshotOut:
    await _ensure_owner(session, device_id=device_id, owner_id=claims["sub"])
    await _upsert_personal(
        device_id=device_id,
        user_id=claims["sub"],
        kind="notifications",
        items=payload.notifications,
        request=request,
        session=session,
    )
    return NotificationSnapshotOut(
        device_id=device_id,
        notifications=payload.notifications,
        updated_at=_iso(_now()),
    )


@router.get(
    "/{device_id}/personal/{kind}",
    summary="Read a personal snapshot (owner-only)",
)
async def read_personal(
    device_id: str = Path(..., min_length=36, max_length=36),
    kind: str = Path(..., min_length=1, max_length=20),
    session: AsyncSession = Depends(get_db),
    claims: dict = Depends(get_current_user),
):
    if kind not in _PERSONAL_KINDS:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_personal_kind", "message": kind},
        )
    await _ensure_owner(session, device_id=device_id, owner_id=claims["sub"])
    row = await device_service.get_personal_snapshot(session, device_id=device_id, kind=kind)
    if row is None:
        return {"device_id": device_id, "kind": kind, "items": [], "updated_at": None, "restricted": False}
    return {
        "device_id": device_id,
        "kind": kind,
        "items": row.payload.get("items", []),
        "updated_at": _iso(row.updated_at),
        "restricted": row.restricted,
    }


# ---- Geofences ------------------------------------------------------------


@router.get(
    "/{device_id}/geofences",
    summary="List the geofences on a device (owner-only)",
    response_model=list[GeofenceOut],
)
async def list_geofences(
    device_id: str = Path(..., min_length=36, max_length=36),
    session: AsyncSession = Depends(get_db),
    claims: dict = Depends(get_current_user),
) -> list[GeofenceOut]:
    await _ensure_owner(session, device_id=device_id, owner_id=claims["sub"])
    rows = await device_service.list_geofences(session, device_id=device_id)
    return [
        GeofenceOut(
            id=r.id,
            name=r.name,
            latitude=r.latitude,
            longitude=r.longitude,
            radius_meters=r.radius_meters,
            created_at=_iso(r.created_at),
        )
        for r in rows
    ]


@router.post(
    "/{device_id}/geofences",
    status_code=status.HTTP_201_CREATED,
    summary="Create a geofence (owner-only)",
    response_model=GeofenceOut,
)
async def create_geofence(
    payload: GeofenceIn,
    device_id: str = Path(..., min_length=36, max_length=36),
    session: AsyncSession = Depends(get_db),
    claims: dict = Depends(get_current_user),
) -> GeofenceOut:
    await _ensure_owner(session, device_id=device_id, owner_id=claims["sub"])
    row = await device_service.create_geofence(
        session,
        device_id=device_id,
        name=payload.name,
        latitude=payload.latitude,
        longitude=payload.longitude,
        radius_meters=payload.radius_meters,
    )
    return GeofenceOut(
        id=row.id,
        name=row.name,
        latitude=row.latitude,
        longitude=row.longitude,
        radius_meters=row.radius_meters,
        created_at=_iso(row.created_at),
    )


@router.delete(
    "/{device_id}/geofences/{fence_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a geofence (owner-only)",
)
async def delete_geofence(
    device_id: str = Path(..., min_length=36, max_length=36),
    fence_id: str = Path(..., min_length=36, max_length=36),
    session: AsyncSession = Depends(get_db),
    claims: dict = Depends(get_current_user),
) -> Response:
    await _ensure_owner(session, device_id=device_id, owner_id=claims["sub"])
    await device_service.delete_geofence(session, device_id=device_id, fence_id=fence_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- Screen-share sessions ----------------------------------------------


@router.post(
    "/{device_id}/screen-share",
    status_code=status.HTTP_201_CREATED,
    summary="Open a screen-share session (owner-only)",
)
async def open_screen_share(
    payload: CommandIn,
    request: Request,
    device_id: str = Path(..., min_length=36, max_length=36),
    session: AsyncSession = Depends(get_db),
    claims: dict = Depends(get_current_user),
):
    device = await _ensure_owner(session, device_id=device_id, owner_id=claims["sub"])
    if device.enrollment_state != "active":
        raise HTTPException(
            status_code=409,
            detail={"code": "device_not_active", "message": device.enrollment_state},
        )
    decision = await check_capability(session, device_id=device_id, capability="screen_share")
    if decision.decision is not ConsentDecision.GRANTED:
        raise HTTPException(
            status_code=403,
            detail={"code": "consent_required", "reason": decision.reason},
        )
    row = await device_service.open_screen_share(
        session,
        device_id=device_id,
        started_by=claims["sub"],
        session_seconds=payload.session_seconds,
    )
    await audit.record_event(
        session,
        event_type="device.screen_share.opened",
        user_id=claims["sub"],
        device_id=device_id,
        ip=_client_ip(request),
        user_agent=_user_agent(request),
        metadata={"session_id": row.id, "session_seconds": payload.session_seconds},
    )
    await session.commit()
    return {
        "session_id": row.id,
        "device_id": device_id,
        "expires_at": _iso(row.expires_at),
        "started_at": _iso(row.started_at),
    }


@router.get(
    "/{device_id}/screen-share/active",
    summary="Read the active screen-share session, if any (owner-only)",
)
async def get_active_screen_share(
    device_id: str = Path(..., min_length=36, max_length=36),
    session: AsyncSession = Depends(get_db),
    claims: dict = Depends(get_current_user),
):
    await _ensure_owner(session, device_id=device_id, owner_id=claims["sub"])
    row = await device_service.latest_screen_share(session, device_id=device_id)
    if row is None:
        return {"active": False}
    return {
        "active": True,
        "session_id": row.id,
        "started_at": _iso(row.started_at),
        "expires_at": _iso(row.expires_at),
        "last_frame_at": _iso(row.last_frame_at),
    }


@router.post(
    "/{device_id}/screen-share/{session_id}/end",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="End a screen-share session (owner or agent)",
)
async def end_screen_share(
    device_id: str = Path(..., min_length=36, max_length=36),
    session_id: str = Path(..., min_length=36, max_length=36),
    reason: str | None = Query(default=None, max_length=40),
    session: AsyncSession = Depends(get_db),
    claims: dict = Depends(get_current_user),
) -> Response:
    await _ensure_owner(session, device_id=device_id, owner_id=claims["sub"])
    await device_service.end_screen_share(session, session_id=session_id, reason=reason)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- Commands -------------------------------------------------------------


# Capability names accepted on the command path.
_COMMAND_CAPABILITIES = {"screenshot", "screen_share", "locate", "lock", "ring"}


@router.post(
    "/{device_id}/command/{capability}",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Send a command to a device (owner-only). Requires consent.",
    response_model=CommandOut,
)
async def send_command(
    payload: CommandIn,
    request: Request,
    device_id: str = Path(..., min_length=36, max_length=36),
    capability: str = Path(..., min_length=1, max_length=30),
    session: AsyncSession = Depends(get_db),
    claims: dict = Depends(get_current_user),
) -> CommandOut:
    if capability not in _COMMAND_CAPABILITIES:
        raise HTTPException(
            status_code=400,
            detail={"code": "unknown_command", "message": capability},
        )
    device = await _ensure_owner(session, device_id=device_id, owner_id=claims["sub"])
    if device.enrollment_state != "active":
        raise HTTPException(
            status_code=409,
            detail={"code": "device_not_active", "message": device.enrollment_state},
        )

    consent_required = capability in {"screenshot", "screen_share", "locate"}
    if consent_required:
        decision = await check_capability(session, device_id=device_id, capability=capability)
        if decision.decision is not ConsentDecision.GRANTED:
            # 403 with explicit code so the dashboard can render an
            # "awaiting approval" CTA. The activity row is still written
            # so the operator can see the request was made and denied
            # because no consent exists.
            await audit.record_event(
                session,
                event_type=f"device.command.{capability}.denied",
                user_id=claims["sub"],
                device_id=device_id,
                ip=_client_ip(request),
                user_agent=_user_agent(request),
                metadata={"reason": decision.reason, "session_seconds": payload.session_seconds},
            )
            await session.commit()
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "consent_required",
                    "message": (
                        "The device owner has not granted this capability yet. "
                        "Approve it on the device first."
                    ),
                    "reason": decision.reason,
                },
            )

    record = await device_service.open_command(
        session,
        device_id=device_id,
        capability=capability,
        user_id=claims["sub"],
        session_seconds=payload.session_seconds,
        reason=payload.reason,
        ip=_client_ip(request),
        user_agent=_user_agent(request),
    )
    return CommandOut(
        command_id=record.id,
        status="pending",
        expires_at=record.expires_at.isoformat(),
        consent_required=consent_required,
    )
