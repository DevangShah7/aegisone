"""``consents`` table — record of a user accepting a document version.

Each acceptance is immutable: once a row is written, withdrawing consent
sets ``revoked_at`` but the historical acceptance stays. Future versions
of the same document (ToS v2, Privacy Policy v2, etc.) get new rows.

A unique constraint on ``(user_id, consent_type, document_version)``
prevents duplicate acceptances for the same document version.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow


class Consent(Base):
    """A single acceptance (or revocation) of a document version."""

    __tablename__ = "consents"

    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        primary_key=True,
        server_default="gen_random_uuid()",
    )

    user_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Free-form discriminator: ``terms_of_service``,
    # ``privacy_policy``, ``device_management``.
    consent_type: Mapped[str] = mapped_column(Text, nullable=False)

    # Document semver (``1.0.0`` / ``2026.01.0``) — opaque to the schema.
    document_version: Mapped[str] = mapped_column(Text, nullable=False)

    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    ip: Mapped[str | None] = mapped_column(INET(), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "consent_type",
            "document_version",
            name="uq_consents_user_type_version",
        ),
        Index("ix_consents_user_type", "user_id", "consent_type"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<Consent user_id={self.user_id} type={self.consent_type!r} "
            f"version={self.document_version!r}>"
        )
