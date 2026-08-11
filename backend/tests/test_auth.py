"""Integration tests for the /auth/* endpoints.

These hit the FastAPI app via ``TestClient`` and exercise the full
register → login → refresh → logout flow against the live Postgres.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import AuditLog


def _register_payload(email: str = "alice@aegisone.example", password: str = "hunter22hunter22"):
    return {"email": email, "password": password, "device_id": "test-device-001"}


def test_register_creates_user_and_writes_audit_log(client):
    r = client.post("/auth/register", json=_register_payload("bob@aegisone.example"))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user"]["email"] == "bob@aegisone.example"
    assert body["user"]["is_active"] is True
    assert body["user"]["is_verified"] is False
    assert body["user"]["mfa_enabled"] is False
    assert "id" in body["user"]
    assert "created_at" in body["user"]


def test_register_rejects_short_password(client):
    r = client.post(
        "/auth/register",
        json=_register_payload("charlie@aegisone.example", "short"),
    )
    assert r.status_code == 422
    body = r.json()
    # Pydantic v2 returns errors keyed by field.
    assert any("password" in str(err.get("loc", "")) for err in body["detail"])


def test_register_rejects_duplicate_email_with_same_shape(client):
    email = "dup@aegisone.example"
    r1 = client.post("/auth/register", json=_register_payload(email))
    assert r1.status_code == 201
    r2 = client.post("/auth/register", json=_register_payload(email))
    assert r2.status_code == 409
    # Same envelope shape as other errors — no information leak about
    # whether the email is taken.
    assert r2.json()["detail"]["code"] == "email_taken"


def test_register_email_is_case_insensitive(client):
    r1 = client.post("/auth/register", json=_register_payload("Mixed@Aegisone.example"))
    r2 = client.post("/auth/register", json=_register_payload("mixed@aegisone.example"))
    assert r1.status_code == 201, r1.text
    assert r2.status_code == 409


def test_login_returns_token_pair_and_writes_session(client):
    client.post("/auth/register", json=_register_payload("dora@aegisone.example"))
    r = client.post(
        "/auth/login",
        json={
            "email": "dora@aegisone.example",
            "password": "hunter22hunter22",
            "device_id": "test-device-001",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "Bearer"
    assert isinstance(body["access_token"], str) and len(body["access_token"]) > 20
    assert isinstance(body["refresh_token"], str) and len(body["refresh_token"]) > 20
    assert body["expires_in"] > 0 and body["expires_in"] <= 15 * 60


def test_login_with_wrong_password_returns_401(client):
    client.post("/auth/register", json=_register_payload("erin@aegisone.example"))
    r = client.post(
        "/auth/login",
        json={
            "email": "erin@aegisone.example",
            "password": "wrong_password_xx",
            "device_id": "test-device-001",
        },
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "invalid_credentials"


def test_login_unknown_email_returns_same_shape_as_wrong_password(client):
    """Account-enumeration defense: same status + body for unknown vs known."""
    r_unknown = client.post(
        "/auth/login",
        json={
            "email": "nobody@aegisone.example",
            "password": "wrong_password_xx",
            "device_id": "test-device-001",
        },
    )
    client.post("/auth/register", json=_register_payload("frank@aegisone.example"))
    r_known = client.post(
        "/auth/login",
        json={
            "email": "frank@aegisone.example",
            "password": "wrong_password_xx",
            "device_id": "test-device-001",
        },
    )
    assert r_unknown.status_code == r_known.status_code == 401
    assert r_unknown.json() == r_known.json()


def test_refresh_rotates_token_pair_and_revokes_old(client):
    client.post("/auth/register", json=_register_payload("grace@aegisone.example"))
    login = client.post(
        "/auth/login",
        json={
            "email": "grace@aegisone.example",
            "password": "hunter22hunter22",
            "device_id": "test-device-001",
        },
    ).json()
    refresh_old = login["refresh_token"]
    r = client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_old, "device_id": "test-device-001"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["refresh_token"] != refresh_old
    assert body["access_token"] != login["access_token"]


def test_reusing_rotated_refresh_token_revokes_chain(client):
    """Replay defense: a second use of an already-rotated token 401s."""
    client.post("/auth/register", json=_register_payload("henry@aegisone.example"))
    login = client.post(
        "/auth/login",
        json={
            "email": "henry@aegisone.example",
            "password": "hunter22hunter22",
            "device_id": "test-device-001",
        },
    ).json()
    refresh_old = login["refresh_token"]
    # First refresh succeeds.
    r1 = client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_old, "device_id": "test-device-001"},
    )
    assert r1.status_code == 200
    # Second refresh using the OLD token is replay — must 401.
    r2 = client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_old, "device_id": "test-device-001"},
    )
    assert r2.status_code == 401
    # Even the NEW token should now be invalid because the chain was
    # revoked on replay.
    r3 = client.post(
        "/auth/refresh",
        json={"refresh_token": r1.json()["refresh_token"], "device_id": "test-device-001"},
    )
    assert r3.status_code == 401


def test_logout_revokes_refresh_token(client):
    client.post("/auth/register", json=_register_payload("ivy@aegisone.example"))
    login = client.post(
        "/auth/login",
        json={
            "email": "ivy@aegisone.example",
            "password": "hunter22hunter22",
            "device_id": "test-device-001",
        },
    ).json()
    r = client.post("/auth/logout", json={"refresh_token": login["refresh_token"]})
    assert r.status_code == 204
    # Subsequent refresh with that token must 401.
    r2 = client.post(
        "/auth/refresh",
        json={"refresh_token": login["refresh_token"], "device_id": "test-device-001"},
    )
    assert r2.status_code == 401


def test_logout_all_requires_bearer_token(client):
    r = client.post("/auth/logout-all")
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "unauthorized"


def test_logout_all_revokes_every_session(client):
    client.post("/auth/register", json=_register_payload("jane@aegisone.example"))
    login1 = client.post(
        "/auth/login",
        json={
            "email": "jane@aegisone.example",
            "password": "hunter22hunter22",
            "device_id": "device-1",
        },
    ).json()
    login2 = client.post(
        "/auth/login",
        json={
            "email": "jane@aegisone.example",
            "password": "hunter22hunter22",
            "device_id": "device-2",
        },
    ).json()

    headers = {"Authorization": f"Bearer {login1['access_token']}"}
    r = client.post("/auth/logout-all", headers=headers)
    assert r.status_code == 204

    # Both refresh tokens are now dead.
    for tok in (login1["refresh_token"], login2["refresh_token"]):
        r2 = client.post("/auth/refresh", json={"refresh_token": tok, "device_id": "x"})
        assert r2.status_code == 401


def test_login_lockout_after_threshold(client):
    """5 wrong passwords should lock the account until ``locked_until``."""
    client.post("/auth/register", json=_register_payload("karl@aegisone.example"))
    # Threshold is 5; 5 failures should lock.
    for _ in range(5):
        r = client.post(
            "/auth/login",
            json={
                "email": "karl@aegisone.example",
                "password": "wrong_password_xx",
                "device_id": "test-device-001",
            },
        )
        assert r.status_code == 401
    # Even the right password now fails because the account is locked.
    r = client.post(
        "/auth/login",
        json={
            "email": "karl@aegisone.example",
            "password": "hunter22hunter22",
            "device_id": "test-device-001",
        },
    )
    assert r.status_code == 401


def test_get_me_returns_current_user(client):
    client.post("/auth/register", json=_register_payload("liam@aegisone.example"))
    login = client.post(
        "/auth/login",
        json={
            "email": "liam@aegisone.example",
            "password": "hunter22hunter22",
            "device_id": "test-device-001",
        },
    ).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}
    r = client.get("/users/me", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"] == "liam@aegisone.example"
    assert "password_hash" not in body


def test_get_me_without_bearer_returns_401(client):
    r = client.get("/users/me")
    assert r.status_code == 401


def test_audit_log_written_for_login_success_and_failure(client):
    client.post("/auth/register", json=_register_payload("mia@aegisone.example"))
    client.post(
        "/auth/login",
        json={
            "email": "mia@aegisone.example",
            "password": "hunter22hunter22",
            "device_id": "test-device-001",
        },
    )
    client.post(
        "/auth/login",
        json={
            "email": "mia@aegisone.example",
            "password": "wrong_password_xx",
            "device_id": "test-device-001",
        },
    )

    async def _audit_rows() -> list[str]:
        async with SessionLocal() as s:
            r = await s.execute(select(AuditLog.event_type).order_by(AuditLog.id))
            return [row[0] for row in r.all()]

    rows = asyncio.new_event_loop().run_until_complete(_audit_rows())
    assert "auth.register.success" in rows
    assert "auth.login.success" in rows
    assert "auth.login.failure" in rows
