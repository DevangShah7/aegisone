"""Audit-log helper.

``record_event`` writes a row to ``audit_logs`` from any service. We
deliberately accept ``session`` as a parameter rather than opening our
own session so the audit row commits (or rolls back) in the same
transaction as the change it's auditing — there is never a window where
"the action happened but the audit didn't get written".
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


async def record_event(
    session: AsyncSession,
    *,
    event_type: str,
    user_id: str | None = None,
    actor_type: str = "user",
    ip: str | None = None,
    user_agent: str | None = None,
    device_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Append one row to ``audit_logs``.

    Args:
        session: the same async session the caller is using for its main
            write — keep this in one transaction.
        event_type: dotted event name (``auth.login.success``,
            ``auth.refresh.reuse``). Required.
        user_id: the subject of the event. May be ``None`` for events
            that predate or don't have a user (failed logins, etc.).
        actor_type: ``user`` / ``system`` / ``admin``. Defaults to ``user``.
        ip: client IP (validated by caller against the trusted-proxy list).
        user_agent: HTTP user-agent header.
        device_id: client-supplied device id.
        metadata: arbitrary JSON-serializable extras. Never put PII here.
    """
    session.add(
        AuditLog(
            event_type=event_type,
            user_id=user_id,
            actor_type=actor_type,
            ip=ip,
            user_agent=user_agent,
            device_id=device_id,
            metadata_json=metadata or {},
        )
    )
    # No await session.flush(); the caller's commit covers it.
