"""Unit tests for ``app.services.permissions`` — no DB needed.

The permission checker is the gate every sensitive command passes
through; its branches are pure over the row data, so we exercise them
against fake ``DeviceConsent``-like rows here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from app.services.permissions import (
    ConsentDecision,
    check_capability,
    is_valid_capability,
)


@dataclass
class _FakeRow:
    """Subset of ``DeviceConsent`` used by ``check_capability``."""

    id: str
    granted_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None


@pytest.mark.asyncio
async def test_check_capability_no_row_returns_prompt():
    result = await check_capability(
        _FakeSession(None),  # type: ignore[arg-type]
        device_id="d",
        capability="screenshot",
    )
    assert result.decision is ConsentDecision.REQUIRES_PROMPT
    assert result.reason == "none"


@pytest.mark.asyncio
async def test_check_capability_active_row_returns_granted():
    now = datetime.now(tz=UTC)
    row = _FakeRow(
        id="c1",
        granted_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(minutes=30),
        revoked_at=None,
    )
    result = await check_capability(
        _FakeSession(row),  # type: ignore[arg-type]
        device_id="d",
        capability="screenshot",
    )
    assert result.decision is ConsentDecision.GRANTED
    assert result.consent_id == "c1"


@pytest.mark.asyncio
async def test_check_capability_revoked_returns_denied():
    now = datetime.now(tz=UTC)
    row = _FakeRow(
        id="c2",
        granted_at=now - timedelta(minutes=10),
        expires_at=None,
        revoked_at=now - timedelta(minutes=1),
    )
    result = await check_capability(
        _FakeSession(row),  # type: ignore[arg-type]
        device_id="d",
        capability="screenshot",
    )
    assert result.decision is ConsentDecision.DENIED
    assert result.reason == "revoked"


@pytest.mark.asyncio
async def test_check_capability_expired_returns_denied():
    now = datetime.now(tz=UTC)
    row = _FakeRow(
        id="c3",
        granted_at=now - timedelta(hours=2),
        expires_at=now - timedelta(minutes=5),  # in the past
        revoked_at=None,
    )
    result = await check_capability(
        _FakeSession(row),  # type: ignore[arg-type]
        device_id="d",
        capability="screenshot",
    )
    assert result.decision is ConsentDecision.DENIED
    assert result.reason == "expired"


@pytest.mark.asyncio
async def test_check_capability_invalid_capability_is_denied():
    result = await check_capability(
        _FakeSession(None),  # type: ignore[arg-type]
        device_id="d",
        capability="telekinesis",
    )
    assert result.decision is ConsentDecision.DENIED
    assert result.reason == "invalid_capability"


def test_is_valid_capability_known_values():
    for c in (
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
    ):
        assert is_valid_capability(c), c


def test_is_valid_capability_rejects_unknown():
    assert not is_valid_capability("")
    assert not is_valid_capability("stealth_mode")
    assert not is_valid_capability("DEVICE_ADMIN")


# ---- helpers --------------------------------------------------------------


class _FakeSession:
    """Tiny stand-in for ``AsyncSession`` that returns the supplied row."""

    def __init__(self, row: _FakeRow | None) -> None:
        self._row = row

    async def execute(self, _stmt):  # pragma: no cover - shape only
        class _R:
            def scalar_one_or_none(self_inner):
                return self._row

        return _R()
