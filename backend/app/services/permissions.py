"""Per-device capability checks.

``require_capability`` is the gate every sensitive command passes
through. It enforces the "explicit, per-session consent on the device"
requirement from the master prompt and ``docs/adr/003-no-covert-operation.md``.

Returns::

    ConsentDecision.GRANTED         — there is an active row.
    ConsentDecision.REQUIRES_PROMPT  — no active row; agent must prompt.
    ConsentDecision.DENIED           — current grant has expired or been
                                       revoked; same surface as
                                       ``REQUIRES_PROMPT`` for the agent
                                       but distinguishable in tests.

Routers must translate ``REQUIRES_PROMPT`` / ``DENIED`` into a HTTP 403
with code ``consent_required`` so the dashboard can show "Awaiting device
owner approval".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CAPABILITIES, DeviceConsent


class ConsentDecision(str, Enum):  # noqa: UP042 - kept as `str, Enum` for cross-runtime compatibility
    """The three states a capability check can return."""

    GRANTED = "granted"
    REQUIRES_PROMPT = "requires_prompt"
    DENIED = "denied"


@dataclass(frozen=True)
class ConsentResult:
    """Detailed result for callers (and tests) that need the reason.

    ``reason`` is one of:

    - ``"none"``             — no row has ever existed for this capability.
    - ``"expired"``          — a row exists but ``expires_at`` has passed.
    - ``"revoked"``          — a row exists but ``revoked_at`` is set.
    - ``"granted"``          — an active row is in force.
    - ``"invalid_capability"`` — the caller passed a string not in ``CAPABILITIES``.
    """

    decision: ConsentDecision
    reason: str
    consent_id: str | None = None


def _now_utc() -> datetime:
    return datetime.now(tz=UTC)


#: Maps the dashboard's command-path capability name to the consent row's
#: capability name. Sensitive commands like ``locate`` are a verb; the
#: consent model uses the noun form ``location``.
_COMMAND_TO_CONSENT: dict[str, str] = {
    "locate": "location",
    "screenshot": "screenshot",
    "screen_share": "screen_share",
}


def is_valid_capability(capability: str) -> bool:
    return capability in CAPABILITIES or capability in _COMMAND_TO_CONSENT


async def check_capability(
    session: AsyncSession,
    *,
    device_id: str,
    capability: str,
) -> ConsentResult:
    """Return ``ConsentResult`` for ``(device_id, capability)``.

    Reads the most recent row matching ``(device_id, capability)``. If
    none exists, ``REQUIRES_PROMPT`` is returned. If the most recent row
    is revoked or expired, ``DENIED`` is returned with a ``reason`` that
    tells the caller why. An active (non-revoked, non-expired) row
    returns ``GRANTED``.

    The ``capability`` argument may be either a consent capability name
    (``location``, ``screenshot`` …) or a dashboard command name
    (``locate``, ``screenshot`` …) — the function maps the verb form to
    the noun form for the lookup.
    """
    consent_capability = _COMMAND_TO_CONSENT.get(capability, capability)
    if not is_valid_capability(consent_capability):
        return ConsentResult(decision=ConsentDecision.DENIED, reason="invalid_capability")

    stmt = (
        select(DeviceConsent)
        .where(DeviceConsent.device_id == device_id, DeviceConsent.capability == consent_capability)
        .order_by(DeviceConsent.granted_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()

    if row is None:
        return ConsentResult(decision=ConsentDecision.REQUIRES_PROMPT, reason="none")

    now = _now_utc()
    if row.revoked_at is not None and row.revoked_at <= now:
        return ConsentResult(
            decision=ConsentDecision.DENIED,
            reason="revoked",
            consent_id=row.id,
        )
    if row.expires_at is not None and row.expires_at <= now:
        return ConsentResult(
            decision=ConsentDecision.DENIED,
            reason="expired",
            consent_id=row.id,
        )
    return ConsentResult(
        decision=ConsentDecision.GRANTED,
        reason="granted",
        consent_id=row.id,
    )
