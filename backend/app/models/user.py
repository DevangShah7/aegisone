"""``users`` table — accounts registered with AegisOne.

Design notes:

- Email is CITEXT (case-insensitive) so ``A@x`` and ``a@x`` collapse to one row.
- Passwords are argon2id, stored as the encoded hash (not the plaintext).
- ``mfa_*`` columns are reserved for the TOTP/Milestone-2 work; nullable.
- ``failed_login_count`` + ``locked_until`` drive the login lockout policy.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, LargeBinary, Text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow


class User(Base):
    """An AegisOne account."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        primary_key=True,
        server_default="gen_random_uuid()",
    )

    email: Mapped[str] = mapped_column(CITEXT(), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Populated in Milestone 2 (TOTP). Nullable today so the schema is
    # forward-compatible with MFA rollout.
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mfa_secret_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # Index on created_at DESC for "recent users" listings.
        Index("ix_users_created_at_desc", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<User id={self.id} email={self.email!r} active={self.is_active}>"
