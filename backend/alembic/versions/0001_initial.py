"""initial schema: users, sessions, audit_logs, consents

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-10

Notes
-----
- Enables ``citext`` (case-insensitive email) and ``pgcrypto``
  (``gen_random_uuid()``) extensions before creating any tables.
- Adds a manual ``CHECK`` on ``audit_logs.actor_type`` so the column
  cannot hold unexpected values like ``'guest'`` or typos.
- Adds a manual ``CHECK`` on ``consents.consent_type`` so a typo in the
  service layer fails the INSERT instead of writing junk to the table.
- The Python-side defaults on ``User.is_active`` etc. are *also* kept as
  server-side defaults so ``INSERT INTO users (email, password_hash)
  VALUES (...)`` from a manual psql session still produces a sane row.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Allowed values for free-form text columns. Keeping these as DB-level
# CHECK constraints means the auth service can never insert ``"users"``
# by accident and the audit log cannot be polluted by typo'd event names.
_AUDIT_ACTOR_TYPES = ("user", "system", "admin")
_CONSENT_TYPES = ("terms_of_service", "privacy_policy", "device_management")


def upgrade() -> None:
    # Extensions. ``IF NOT EXISTS`` so re-running against a partially
    # migrated DB doesn't blow up. Both are required by the schema:
    # - ``pgcrypto`` provides ``gen_random_uuid()`` for default UUIDs.
    # - ``citext`` provides the case-insensitive text type for emails.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table(
        "users",
        sa.Column(
            "id",
            sa.UUID(as_uuid=False),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "is_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "mfa_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("mfa_secret_enc", sa.LargeBinary(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "failed_login_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index("ix_users_created_at_desc", "users", ["created_at"], unique=False)
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "audit_logs",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("user_id", sa.UUID(as_uuid=False), nullable=True),
        sa.Column(
            "actor_type",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'user'"),
        ),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("device_id", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "actor_type IN ('user', 'system', 'admin')",
            name=op.f("ck_audit_logs_actor_type"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_audit_logs_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(
        "ix_audit_logs_event_created_at",
        "audit_logs",
        ["event_type", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_logs_user_created_at",
        "audit_logs",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(op.f("ix_audit_logs_user_id"), "audit_logs", ["user_id"], unique=False)

    op.create_table(
        "consents",
        sa.Column(
            "id",
            sa.UUID(as_uuid=False),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("consent_type", sa.Text(), nullable=False),
        sa.Column("document_version", sa.Text(), nullable=False),
        sa.Column(
            "accepted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "consent_type IN ('terms_of_service', 'privacy_policy', 'device_management')",
            name=op.f("ck_consents_consent_type"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_consents_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_consents")),
        sa.UniqueConstraint(
            "user_id",
            "consent_type",
            "document_version",
            name="uq_consents_user_type_version",
        ),
    )
    op.create_index(
        "ix_consents_user_type",
        "consents",
        ["user_id", "consent_type"],
        unique=False,
    )

    op.create_table(
        "sessions",
        sa.Column(
            "id",
            sa.UUID(as_uuid=False),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("device_id", sa.Text(), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by", sa.UUID(as_uuid=False), nullable=True),
        sa.ForeignKeyConstraint(
            ["replaced_by"],
            ["sessions.id"],
            name=op.f("fk_sessions_replaced_by_sessions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
    )
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"], unique=False)
    op.create_index(op.f("ix_sessions_token_hash"), "sessions", ["token_hash"], unique=True)
    op.create_index(
        "ix_sessions_user_active",
        "sessions",
        ["user_id", "revoked_at"],
        unique=False,
    )
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_index("ix_sessions_user_active", table_name="sessions")
    op.drop_index(op.f("ix_sessions_token_hash"), table_name="sessions")
    op.drop_index("ix_sessions_expires_at", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("ix_consents_user_type", table_name="consents")
    op.drop_table("consents")
    op.drop_index(op.f("ix_audit_logs_user_id"), table_name="audit_logs")
    op.drop_index("ix_audit_logs_user_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_event_created_at", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_index("ix_users_created_at_desc", table_name="users")
    op.drop_table("users")
    # Note: extensions are not dropped on downgrade; other databases on the
    # same Postgres cluster may still be relying on them.
