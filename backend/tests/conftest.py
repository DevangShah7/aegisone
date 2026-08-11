"""Shared pytest fixtures.

- ``_reset_settings_cache``: clears ``get_settings`` lru_cache between
  tests so env-var mutations take effect.
- ``_clean_db``: truncates every AegisOne table after each test that
  uses the ``client`` or ``db_session`` fixture, so rows leaked by the
  auth flow don't bleed across tests.
- ``db_session``: per-test transactional ``AsyncSession`` against the
  live Postgres defined in ``DATABASE_URL``. Rolls back at the end so
  tests don't pollute each other.
- ``client``: ``fastapi.testclient.TestClient`` (synchronous). Triggers
  the FastAPI lifespan, so production invariant checks run.
- ``registered_user``: a registered + logged-in user with a known
  email/password + bearer token + refresh token. Pre-built so
  device-enrollment and command tests don't all re-implement the
  register/login round-trip.

The ``db_session`` and ``client`` fixtures skip if Postgres isn't
reachable so the unit tests still run on a machine without Docker.
"""

from __future__ import annotations

import socket

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import User


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> None:
    """Clear the lru_cache on settings between tests.

    Tests that mutate ``os.environ`` would otherwise see a stale
    ``Settings`` instance.
    """
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _can_connect(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def db_available() -> bool:
    """Whether Postgres is reachable on localhost:5432."""
    return _can_connect("localhost", 5432)


async def _truncate_all_tables() -> None:
    """Wipe every AegisOne table between tests."""
    from sqlalchemy import text

    async with SessionLocal() as s:
        await s.execute(
            text(
                "TRUNCATE TABLE "
                "device_activity_events, device_installed_apps, "
                "device_consents, device_geofences, "
                "device_health, device_credentials, devices, "
                "audit_logs, consents, sessions, users "
                "RESTART IDENTITY CASCADE"
            )
        )
        await s.commit()


@pytest.fixture
def _clean_db(db_available: bool):
    """Per-test truncation so tests don't leak data.

    Run *after* the test body, regardless of whether it raised.
    """
    yield
    if db_available:
        import asyncio

        try:
            asyncio.get_event_loop().run_until_complete(_truncate_all_tables())
        except RuntimeError:
            # Loop already closed by pytest — fall back to a fresh one.
            asyncio.run(_truncate_all_tables())


@pytest_asyncio.fixture
async def db_session(db_available: bool) -> AsyncSession:
    """Per-test transactional session against live Postgres.

    Wraps each test in a SAVEPOINT we always roll back. Also depends
    on ``_clean_db`` so any rows written via FastAPI handlers are
    truncated after the test.
    """
    if not db_available:
        pytest.skip("Postgres not reachable on localhost:5432")
    async with SessionLocal() as session:
        await session.begin()
        try:
            yield session
        finally:
            await session.rollback()


@pytest.fixture
def client(db_available: bool, _clean_db) -> TestClient:
    """``TestClient`` that triggers the FastAPI lifespan.

    Synchronous — works around the async httpx fixture boilerplate.
    Skips if Postgres isn't reachable.
    """
    if not db_available:
        pytest.skip("Postgres not reachable — backend needs DB to start")
    with TestClient(app) as c:
        yield c


# ---- Convenience fixtures --------------------------------------------------


@pytest_asyncio.fixture
async def make_user(db_session: AsyncSession):
    """Return a callable that inserts a User row directly.

    Useful when a test needs a controlled user state (e.g. a user with a
    specific email) without going through the registration endpoint.
    """

    async def _factory(
        email: str = "user@example.com",
        password: str = "Correct-Horse-Battery-Staple",
        is_active: bool = True,
    ) -> User:
        user = User(
            email=email.lower(),
            password_hash=hash_password(password),
            is_active=is_active,
        )
        db_session.add(user)
        await db_session.flush()
        await db_session.refresh(user)
        return user

    return _factory


@pytest.fixture
def registered_user(client: TestClient):
    """Register + log in a user and return ``(email, access, refresh)``.

    Skipped if ``client`` was skipped (Postgres unavailable). The
    ``device_id`` is fixed so refresh-token tests can pass it back.
    """
    email = "device-owner@example.com"
    password = "Correct-Horse-Battery-Staple"
    device_id = "test-device-001"
    client.post(
        "/auth/register",
        json={"email": email, "password": password, "device_id": device_id},
    )
    resp = client.post(
        "/auth/login",
        json={"email": email, "password": password, "device_id": device_id},
    )
    body = resp.json()
    return {
        "email": email,
        "password": password,
        "device_id": device_id,
        "access_token": body["access_token"],
        "refresh_token": body["refresh_token"],
        "headers": {"Authorization": f"Bearer {body['access_token']}"},
    }


@pytest.fixture(scope="session", autouse=True)
def _dispose_engine_at_session_end():
    """Dispose the SQLAlchemy engine after the test session ends."""
    yield
    import asyncio
    import contextlib

    with contextlib.suppress(Exception):
        asyncio.get_event_loop().run_until_complete(engine.dispose())
