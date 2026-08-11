"""device registry: devices, credentials, health, consents, events, apps, geofences

Revision ID: 0002_device_registry
Revises: 0001_initial
Create Date: 2026-08-10

Notes
-----
- Mirrors the SQLAlchemy models in ``app/models/device.py`` exactly.
  Run ``alembic upgrade head`` and ``alembic downgrade base`` to verify
  the upgrade + downgrade are inverses.
- Adding ``capability`` and ``enrollment_state`` as free text columns
  with CHECK constraints so a typo'd value fails the INSERT in a
  visible place (``capability`` only — ``enrollment_state``'s allowed
  values are baked into the DB-level CHECK).
- ``device_activity_events`` and ``device_installed_apps`` use BIGSERIAL
  PKs because they are append-heavy.
- Pairing codes live in an in-memory store keyed by code → no table.
  We rely on the application-layer eviction; the device row is the
  durable anchor.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_device_registry"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Allowed values mirrored from ``app.models.device``.
_ENROLLMENT_STATES = ("pending", "active", "revoked")
_CAPABILITIES = (
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
)


def upgrade() -> None:
    # ---- devices ---------------------------------------------------------
    op.create_table(
        "devices",
        sa.Column(
            "id",
            sa.UUID(as_uuid=False),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("owner_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("hardware_model", sa.String(length=120), nullable=True),
        sa.Column("os_version", sa.String(length=60), nullable=True),
        sa.Column("app_version", sa.String(length=60), nullable=True),
        sa.Column("battery_pct", sa.Integer(), nullable=True),
        sa.Column("network_type", sa.String(length=40), nullable=True),
        sa.Column(
            "enrollment_state",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
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
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "enrollment_state IN ('pending','active','revoked')",
            name=op.f("ck_devices_enrollment_state"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_devices_owner_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_devices")),
    )
    op.create_index(
        "ix_devices_owner_last_seen",
        "devices",
        ["owner_id", "last_seen_at"],
        unique=False,
    )
    op.create_index(op.f("ix_devices_owner_id"), "devices", ["owner_id"], unique=False)

    # ---- device_credentials ---------------------------------------------
    op.create_table(
        "device_credentials",
        sa.Column("device_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("refresh_token_hash", sa.Text(), nullable=False),
        sa.Column("keystore_alias", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.id"],
            name=op.f("fk_device_credentials_device_id_devices"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("device_id", name=op.f("pk_device_credentials")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_device_credentials_token_hash")),
    )
    op.create_index(
        op.f("ix_device_credentials_refresh_token_hash"),
        "device_credentials",
        ["refresh_token_hash"],
        unique=False,
    )
    op.create_index(
        op.f("ix_device_credentials_token_hash"),
        "device_credentials",
        ["token_hash"],
        unique=True,
    )

    # ---- device_health --------------------------------------------------
    op.create_table(
        "device_health",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("device_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("battery_pct", sa.Integer(), nullable=True),
        sa.Column("network_type", sa.String(length=40), nullable=True),
        sa.Column(
            "is_charging",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("free_storage_mb", sa.BigInteger(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.id"],
            name=op.f("fk_device_health_device_id_devices"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_device_health")),
    )
    op.create_index(
        "ix_device_health_device_recorded",
        "device_health",
        ["device_id", "recorded_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_device_health_device_id"), "device_health", ["device_id"], unique=False
    )

    # ---- device_consents -------------------------------------------------
    op.create_table(
        "device_consents",
        sa.Column(
            "id",
            sa.UUID(as_uuid=False),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("device_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("capability", sa.String(length=40), nullable=False),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "capability IN ('location','screenshot','camera','microphone',"
            "'screen_share','contacts','calendar','sms','notifications','backup')",
            name=op.f("ck_device_consents_capability"),
        ),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.id"],
            name=op.f("fk_device_consents_device_id_devices"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_device_consents_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_device_consents")),
    )
    op.create_index(
        "ix_device_consents_device_capability",
        "device_consents",
        ["device_id", "capability"],
        unique=False,
    )

    # ---- device_activity_events -----------------------------------------
    op.create_table(
        "device_activity_events",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("device_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.id"],
            name=op.f("fk_device_activity_events_device_id_devices"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_device_activity_events")),
    )
    op.create_index(
        "ix_device_activity_device_occurred",
        "device_activity_events",
        ["device_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_device_activity_event_occurred",
        "device_activity_events",
        ["event_type", "occurred_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_device_activity_events_device_id"),
        "device_activity_events",
        ["device_id"],
        unique=False,
    )

    # ---- device_installed_apps -----------------------------------------
    op.create_table(
        "device_installed_apps",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("device_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("package_name", sa.String(length=255), nullable=False),
        sa.Column("app_label", sa.String(length=255), nullable=True),
        sa.Column("version_name", sa.String(length=60), nullable=True),
        sa.Column("version_code", sa.Integer(), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.id"],
            name=op.f("fk_device_installed_apps_device_id_devices"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_device_installed_apps")),
        sa.UniqueConstraint("device_id", "package_name", name="uq_device_app_package"),
    )
    op.create_index("ix_device_apps_device", "device_installed_apps", ["device_id"], unique=False)

    # ---- device_geofences ---------------------------------------------
    op.create_table(
        "device_geofences",
        sa.Column(
            "id",
            sa.UUID(as_uuid=False),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("device_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column(
            "radius_meters",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("200"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.id"],
            name=op.f("fk_device_geofences_device_id_devices"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_device_geofences")),
    )
    op.create_index(
        op.f("ix_device_geofences_device_id"),
        "device_geofences",
        ["device_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_device_geofences_device_id"), table_name="device_geofences")
    op.drop_table("device_geofences")

    op.drop_index("ix_device_apps_device", table_name="device_installed_apps")
    op.drop_table("device_installed_apps")

    op.drop_index(op.f("ix_device_activity_events_device_id"), table_name="device_activity_events")
    op.drop_index("ix_device_activity_event_occurred", table_name="device_activity_events")
    op.drop_index("ix_device_activity_device_occurred", table_name="device_activity_events")
    op.drop_table("device_activity_events")

    op.drop_index("ix_device_consents_device_capability", table_name="device_consents")
    op.drop_table("device_consents")

    op.drop_index(op.f("ix_device_health_device_id"), table_name="device_health")
    op.drop_index("ix_device_health_device_recorded", table_name="device_health")
    op.drop_table("device_health")

    op.drop_index(op.f("ix_device_credentials_token_hash"), table_name="device_credentials")
    op.drop_index(
        op.f("ix_device_credentials_refresh_token_hash"),
        table_name="device_credentials",
    )
    op.drop_table("device_credentials")

    op.drop_index(op.f("ix_devices_owner_id"), table_name="devices")
    op.drop_index("ix_devices_owner_last_seen", table_name="devices")
    op.drop_table("devices")
