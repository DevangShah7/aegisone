"""``sessions`` table — one row per active refresh token.

Refresh tokens are opaque random strings; only the sha256 hex digest is
stored. Rotation works by inserting a new row and pointing the old row's
``replaced_by`` at it. If the old token ever shows up again (replay
attack), we revoke every row in the chain by walking ``replaced_by`` from
the matched row backwards to its root.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow


class Session(Base):
    """A single active refresh-token session for a user/device pair."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        primary_key=True,
        server_default="gen_random_uuid()",
    )

    user_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Client-supplied device identifier (mobile/UUID). Stored as text so we
    # don't impose a UUID format on every client.
    device_id: Mapped[str] = mapped_column(Text, nullable=False)

    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str | None] = mapped_column(INET(), nullable=True)

    # sha256 hex of the raw refresh token. Used for lookup; never the raw.
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # When this row is rotated, ``replaced_by`` points at the successor.
    # Walking ``replaced_by`` from a reused token back to its root gives us
    # the full chain to revoke.
    replaced_by: Mapped[str | None] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_sessions_user_active", "user_id", "revoked_at"),
        Index("ix_sessions_expires_at", "expires_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Session id={self.id} user_id={self.user_id} device={self.device_id!r}>"
