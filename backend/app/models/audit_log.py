"""``audit_logs`` table — append-only event log.

Every authentication / authorization event writes a row. Designed for
high write volume, so the PK is BIGINT and the schema keeps the row
size small (no ``text`` columns beyond user_agent).

The ``metadata`` JSONB column is a free-form bag for event-specific
extras (``{"reason": "bad_password"}``, ``{"device_id": "..."}``, etc).
Never put PII in here.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow


class AuditLog(Base):
    """A single audit event."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement="auto")

    user_id: Mapped[str | None] = mapped_column(
        PGUUID(as_uuid=False),
        # ON DELETE SET NULL — we keep the audit row even if the user is
        # later deleted; ``user_id`` becomes NULL but the event remains.
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ``user`` | ``system`` | ``admin``. Defaults to ``user``; explicit so
    # background jobs don't accidentally appear as a real user.
    actor_type: Mapped[str] = mapped_column(Text, nullable=False, default="user")
    # Domain-prefixed event name, e.g. ``auth.login.success``,
    # ``auth.refresh.reuse``, ``device.pair``.
    event_type: Mapped[str] = mapped_column(Text, nullable=False)

    ip: Mapped[str | None] = mapped_column(INET(), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    device_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    metadata_json: Mapped[dict] = mapped_column(
        "metadata",  # column name in Postgres is ``metadata``; ``metadata``
        # is reserved in SQLAlchemy declarative.
        JSONB,
        nullable=False,
        default=dict,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        # Most queries are "give me events for this user in the last week"
        # or "show me every login.failure in the last hour" — both
        # composite indexes ordered by created_at DESC.
        Index("ix_audit_logs_user_created_at", "user_id", "created_at"),
        Index("ix_audit_logs_event_created_at", "event_type", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<AuditLog id={self.id} event_type={self.event_type!r}>"
