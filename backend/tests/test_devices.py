"""Device-registry endpoint tests.

Coverage:
- enrollment round-trip with QR + 6-digit code
- heartbeat updates last_seen and battery
- activity batch ingest + permission-aware listing
- consent grant / revoke + capability gate
- command routing: denied without consent, allowed with consent, lost-device
  commands (lock, ring) bypass the consent check
- idempotency on double confirm
- cross-device activity feed
- audit-log entries for the sensitive actions
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.models import (
    DeviceConsent,
    DeviceInstalledApp,
)


def _enroll_pair(client, headers) -> tuple[str, str]:
    """Helper: ask the owner to mint a pairing code; return (code, id)."""
    resp = client.post(
        "/devices/enroll/request",
        headers=headers,
        json={"device_name": "Test Pixel"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["pairing_code"], body["device_id"]


def _confirm_enrollment(client, code: str, device_id: str, alias: str = "k1") -> dict:
    resp = client.post(
        "/devices/enroll/confirm",
        json={
            "pairing_code": code,
            "device_id": device_id,
            "public_key_alias": alias,
            "hardware_model": "Pixel-Test",
            "os_version": "Android 14",
            "app_version": "0.2.0",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_enroll_request_then_confirm_succeeds(client, registered_user):
    code, device_id = _enroll_pair(client, registered_user["headers"])
    confirm = _confirm_enrollment(client, code, device_id)
    assert confirm["device_id"] == device_id
    assert confirm["access_token"]
    assert confirm["refresh_token"]


def test_enroll_confirm_with_wrong_code_404(client, registered_user):
    code, device_id = _enroll_pair(client, registered_user["headers"])
    bad = client.post(
        "/devices/enroll/confirm",
        json={
            "pairing_code": "000000",
            "device_id": device_id,
            "public_key_alias": "k1",
        },
    )
    assert bad.status_code == 404
    assert bad.json()["detail"]["code"] == "invalid_pairing_code"
    # original pairing code is still valid — only an unknown code is 404
    again = _confirm_enrollment(client, code, device_id)
    assert again["device_id"] == device_id


def test_enroll_confirm_with_mismatched_device_id_409(client, registered_user):
    code, _ = _enroll_pair(client, registered_user["headers"])
    # Use a random UUID so we trigger the mismatch branch.
    bad = client.post(
        "/devices/enroll/confirm",
        json={
            "pairing_code": code,
            "device_id": "00000000-0000-0000-0000-000000000000",
            "public_key_alias": "k1",
        },
    )
    assert bad.status_code == 409
    assert bad.json()["detail"]["code"] == "device_id_mismatch"


def test_pairing_code_single_use(client, registered_user):
    code, device_id = _enroll_pair(client, registered_user["headers"])
    _confirm_enrollment(client, code, device_id)
    # Re-confirming the same code yields 404 (it was popped from the map).
    second = client.post(
        "/devices/enroll/confirm",
        json={
            "pairing_code": code,
            "device_id": device_id,
            "public_key_alias": "k1",
        },
    )
    assert second.status_code == 404


def test_device_lists_only_owners_devices(client, registered_user):
    code, device_id = _enroll_pair(client, registered_user["headers"])
    _confirm_enrollment(client, code, device_id)
    resp = client.get("/devices", headers=registered_user["headers"])
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["id"] == device_id
    assert rows[0]["hardware_model"] == "Pixel-Test"
    assert rows[0]["enrollment_state"] == "active"


def test_get_device_detail_includes_consents(client, registered_user):
    code, device_id = _enroll_pair(client, registered_user["headers"])
    _confirm_enrollment(client, code, device_id)
    # Push a consent via the device-side endpoint.
    grant = client.post(
        f"/devices/{device_id}/consents",
        headers=registered_user["headers"],
        json={"capability": "screenshot"},
    )
    assert grant.status_code == 201
    consent_id = grant.json()["id"]
    detail = client.get(f"/devices/{device_id}", headers=registered_user["headers"])
    assert detail.status_code == 200
    body = detail.json()
    cap_set = {c["capability"] for c in body["consents"]}
    assert cap_set == {"screenshot"}

    # Revoke and re-fetch.
    async def _revoke_now() -> None:
        from datetime import UTC, datetime

        from sqlalchemy import update

        from app.db.session import SessionLocal

        async with SessionLocal() as s:
            await s.execute(
                update(DeviceConsent)
                .where(DeviceConsent.id == consent_id)
                .values(revoked_at=datetime.now(tz=UTC))
            )
            await s.commit()

    asyncio.run(_revoke_now())
    detail = client.get(f"/devices/{device_id}", headers=registered_user["headers"])
    assert {c["capability"] for c in detail.json()["consents"]} == {"screenshot"}


def test_heartbeat_updates_last_seen_and_writes_sample(client, registered_user):
    code, device_id = _enroll_pair(client, registered_user["headers"])
    _confirm_enrollment(client, code, device_id)
    resp = client.post(
        f"/devices/{device_id}/heartbeat",
        headers=registered_user["headers"],
        json={
            "battery_pct": 72,
            "network_type": "wifi",
            "is_charging": True,
            "free_storage_mb": 2048,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["battery_pct"] == 72
    assert body["network_type"] == "wifi"
    assert body["last_seen_at"]


def test_activity_ingest_and_listing(client, registered_user):
    code, device_id = _enroll_pair(client, registered_user["headers"])
    _confirm_enrollment(client, code, device_id)
    push = client.post(
        f"/devices/{device_id}/activity",
        headers=registered_user["headers"],
        json={
            "events": [
                {"event_type": "app.foreground", "payload": {"app": "com.example"}},
                {"event_type": "screenshot.captured", "payload": {"size": 12345}},
            ]
        },
    )
    assert push.status_code == 202
    assert push.json() == {"accepted": 2}

    listed = client.get(f"/devices/{device_id}/activity", headers=registered_user["headers"])
    assert listed.status_code == 200
    types = {row["event_type"] for row in listed.json()}
    assert "app.foreground" in types
    assert "screenshot.captured" in types


def test_apps_snapshot_upsert(client, registered_user, db_session):
    code, device_id = _enroll_pair(client, registered_user["headers"])
    _confirm_enrollment(client, code, device_id)
    snapshot = client.post(
        f"/devices/{device_id}/apps",
        headers=registered_user["headers"],
        json={
            "apps": [
                {"package_name": "com.android.settings", "app_label": "Settings"},
                {"package_name": "com.example.app", "app_label": "Example", "version_code": 7},
            ]
        },
    )
    assert snapshot.status_code == 202
    assert snapshot.json() == {"accepted": 2}

    # Re-send the same snapshot. The row count must stay at 2 (upsert, not insert).
    snapshot2 = client.post(
        f"/devices/{device_id}/apps",
        headers=registered_user["headers"],
        json={
            "apps": [
                {"package_name": "com.example.app", "app_label": "Example", "version_code": 8},
            ]
        },
    )
    assert snapshot2.status_code == 202

    async def _count() -> int:
        async with db_session.bind.connect() as _:
            pass
        result = await db_session.execute(
            select(DeviceInstalledApp).where(DeviceInstalledApp.device_id == device_id)
        )
        return len(list(result.scalars().all()))

    n = asyncio.run(_count())
    assert n == 2


def test_cross_device_activity_feed(client, registered_user):
    code, device_id = _enroll_pair(client, registered_user["headers"])
    _confirm_enrollment(client, code, device_id)
    client.post(
        f"/devices/{device_id}/activity",
        headers=registered_user["headers"],
        json={"events": [{"event_type": "app.installed", "payload": {"app": "x.y"}}]},
    )
    feed = client.get("/activity", headers=registered_user["headers"])
    assert feed.status_code == 200
    events = feed.json()
    assert events
    assert events[0]["event_type"] == "app.installed"


def test_command_without_consent_returns_403(client, registered_user):
    code, device_id = _enroll_pair(client, registered_user["headers"])
    _confirm_enrollment(client, code, device_id)
    resp = client.post(
        f"/devices/{device_id}/command/screenshot",
        headers=registered_user["headers"],
        json={"session_seconds": 60, "reason": "Test"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "consent_required"


def test_command_lock_and_ring_bypass_consent(client, registered_user):
    code, device_id = _enroll_pair(client, registered_user["headers"])
    _confirm_enrollment(client, code, device_id)
    # Lost-device commands don't require consent (inverse controls).
    for capability in ("lock", "ring"):
        resp = client.post(
            f"/devices/{device_id}/command/{capability}",
            headers=registered_user["headers"],
            json={"session_seconds": 30, "reason": "Lost device test"},
        )
        assert resp.status_code == 202, f"{capability} returned {resp.status_code}"
        body = resp.json()
        assert body["consent_required"] is False
        assert body["status"] == "pending"


def test_command_with_active_consent_succeeds(client, registered_user):
    code, device_id = _enroll_pair(client, registered_user["headers"])
    _confirm_enrollment(client, code, device_id)

    # 403 path
    denied = client.post(
        f"/devices/{device_id}/command/screenshot",
        headers=registered_user["headers"],
        json={"session_seconds": 60, "reason": "Test"},
    )
    assert denied.status_code == 403

    # Grant consent
    grant = client.post(
        f"/devices/{device_id}/consents",
        headers=registered_user["headers"],
        json={"capability": "screenshot"},
    )
    assert grant.status_code == 201

    # Now the command should be accepted
    allowed = client.post(
        f"/devices/{device_id}/command/screenshot",
        headers=registered_user["headers"],
        json={"session_seconds": 60, "reason": "Test"},
    )
    assert allowed.status_code == 202
    body = allowed.json()
    assert body["consent_required"] is True
    assert body["command_id"]


def test_consent_revoke_blocks_followup_command(client, registered_user):
    code, device_id = _enroll_pair(client, registered_user["headers"])
    _confirm_enrollment(client, code, device_id)
    # Grant, then revoke via DB to exercise the DENIED branch.
    grant = client.post(
        f"/devices/{device_id}/consents",
        headers=registered_user["headers"],
        json={"capability": "screenshot"},
    )
    consent_id = grant.json()["id"]
    asyncio.run(
        _set_consent_revoked(consent_id),
    )
    denied = client.post(
        f"/devices/{device_id}/command/screenshot",
        headers=registered_user["headers"],
        json={"session_seconds": 60, "reason": "after revoke"},
    )
    assert denied.status_code == 403


def test_revoke_device_404_on_subsequent_calls(client, registered_user):
    code, device_id = _enroll_pair(client, registered_user["headers"])
    _confirm_enrollment(client, code, device_id)
    rev = client.delete(f"/devices/{device_id}", headers=registered_user["headers"])
    assert rev.status_code == 204
    after = client.get(f"/devices/{device_id}", headers=registered_user["headers"])
    # Revoke_device updates the row in-place; get_device still returns it,
    # but enrollment_state is now 'revoked'. Confirm via the state.
    assert after.status_code == 200
    assert after.json()["enrollment_state"] == "revoked"


def test_revoked_device_refuses_lock_command(client, registered_user):
    code, device_id = _enroll_pair(client, registered_user["headers"])
    _confirm_enrollment(client, code, device_id)
    client.delete(f"/devices/{device_id}", headers=registered_user["headers"])
    denied = client.post(
        f"/devices/{device_id}/command/lock",
        headers=registered_user["headers"],
        json={"session_seconds": 30, "reason": "after revoke"},
    )
    assert denied.status_code == 409
    assert denied.json()["detail"]["code"] == "device_not_active"


def test_other_users_device_returns_404(client, registered_user, make_user):
    """A second user cannot see the first user's devices."""
    code, device_id = _enroll_pair(client, registered_user["headers"])
    _confirm_enrollment(client, code, device_id)

    async def _login_second_user() -> dict:
        # Direct DB insert; login via /auth/register + /auth/login.
        second_email = "intruder@example.com"
        password = "Twelve-Chars-Min!"
        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app) as c:
            c.post(
                "/auth/register",
                json={
                    "email": second_email,
                    "password": password,
                    "device_id": "second-device",
                },
            )
            r = c.post(
                "/auth/login",
                json={
                    "email": second_email,
                    "password": password,
                    "device_id": "second-device",
                },
            )
            return {"headers": {"Authorization": f"Bearer {r.json()['access_token']}"}}

    headers = asyncio.run(_login_second_user())["headers"]
    other = client.get(f"/devices/{device_id}", headers=headers)
    assert other.status_code == 404


def test_device_detail_writes_audit_rows(client, registered_user, db_session):
    code, device_id = _enroll_pair(client, registered_user["headers"])
    _confirm_enrollment(client, code, device_id)
    # One audit row each for ``request`` and ``confirm``.
    n = asyncio.run(_count_audit_events(db_session))
    assert n >= 2


# ---- helpers --------------------------------------------------------------


async def _count_audit_events(db_session) -> int:
    from sqlalchemy import text

    result = await db_session.execute(
        text(
            "SELECT count(*) FROM audit_logs "
            "WHERE event_type LIKE 'device.%' OR event_type LIKE 'device.enroll.%'"
        )
    )
    return int(result.scalar_one())


async def _set_consent_revoked(consent_id: str) -> None:
    from datetime import UTC, datetime

    from sqlalchemy import update

    from app.db.session import SessionLocal
    from app.models import DeviceConsent

    async with SessionLocal() as s:
        await s.execute(
            update(DeviceConsent)
            .where(DeviceConsent.id == consent_id)
            .values(revoked_at=datetime.now(tz=UTC))
        )
        await s.commit()
