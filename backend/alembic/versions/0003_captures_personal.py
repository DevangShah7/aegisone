"""captures + personal snapshots + screen-share sessions

Revision ID: 0003_captures_personal_screenshare
Revises: 0002_device_registry
Create Date: 2026-08-11

Adds three tables that did not exist in 0002 but are now required by the
'Everything in the dashboard' feature slice:

- ``device_captures``              — inline base64 media blobs (screenshot,
                                    camera diagnostic snapshot, microphone
                                    clip). Mime-typed + sized so the contract
                                    can swap to MinIO later.
- ``device_personal_snapshots``    — last-known snapshot of
                                    contacts / calendar / SMS / notifications
                                    per device. ``restricted`` flag carries
                                    the Android 13+ READ_SMS gate state.
- ``device_screen_share_sessions`` — ongoing screen-share session rows
                                    (start / end + last-frame timestamp +
                                    hard expiry).
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_captures_personal"
down_revision: str | None = "0002_device_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "device_captures",
        sa.Column("id", sa.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("device_id", sa.UUID(as_uuid=False), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("mime_type", sa.String(80), nullable=False),
        sa.Column("bytes_size", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "kind IN ('screenshot','camera','microphone')",
            name="ck_device_captures_kind",
        ),
    )
    op.create_index(
        "ix_device_captures_device_captured",
        "device_captures",
        ["device_id", "captured_at"],
    )

    op.create_table(
        "device_personal_snapshots",
        sa.Column("id", sa.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("device_id", sa.UUID(as_uuid=False), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("restricted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("device_id", "kind", name="uq_device_personal_kind"),
        sa.CheckConstraint(
            "kind IN ('contacts','calendar','sms','notifications')",
            name="ck_device_personal_kind",
        ),
    )

    op.create_table(
        "device_screen_share_sessions",
        sa.Column("id", sa.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("device_id", sa.UUID(as_uuid=False), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_by", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_frame_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_reason", sa.String(40), nullable=True),
    )
    op.create_index(
        "ix_device_screen_share_device",
        "device_screen_share_sessions",
        ["device_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_device_screen_share_device", table_name="device_screen_share_sessions")
    op.drop_table("device_screen_share_sessions")
    op.drop_table("device_personal_snapshots")
    op.drop_index("ix_device_captures_device_captured", table_name="device_captures")
    op.drop_table("device_captures")
