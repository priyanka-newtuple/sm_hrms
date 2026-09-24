"""Add notifications table.

Revision ID: 202604270003
Revises: 202604270002
Create Date: 2026-04-27 00:03:00
"""

from __future__ import annotations

import os

from alembic import op
import sqlalchemy as sa

revision = "202604270003"
down_revision = "202604270002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")

    op.create_table(
        "notifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey(f"{schema}.organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "recipient_id",
            sa.String(36),
            sa.ForeignKey(f"{schema}.users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("notification_type", sa.String(32), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=True),
        sa.Column("source_id", sa.String(36), nullable=True),
        sa.Column("entity_id", sa.String(36), nullable=False, index=True),
        sa.Column("entity_type", sa.String(128), nullable=False),
        sa.Column("actor_id", sa.String(36), nullable=True),
        sa.Column("actor_name", sa.String(256), nullable=True),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("link", sa.String(512), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema=schema,
    )

    op.create_index(
        "ix_notifications_recipient_unread",
        "notifications",
        ["recipient_id", "is_read"],
        schema=schema,
    )
    op.create_index(
        "ix_notifications_created_at",
        "notifications",
        ["created_at"],
        schema=schema,
    )
    op.create_index(
        "ix_notifications_org_recipient",
        "notifications",
        ["organization_id", "recipient_id"],
        schema=schema,
    )


def downgrade() -> None:
    schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")

    op.drop_index("ix_notifications_org_recipient", table_name="notifications", schema=schema)
    op.drop_index("ix_notifications_created_at", table_name="notifications", schema=schema)
    op.drop_index("ix_notifications_recipient_unread", table_name="notifications", schema=schema)
    op.drop_table("notifications", schema=schema)
