"""Add unified audit_events table.

A single consolidated audit table that captures all system events going
forward — entity events, transition attempts, auth events, comments. The
existing 3 audit tables (entity_events, transition_attempts, auth_events)
are kept as-is and continue to receive writes via dual-write. No backfill.

Revision ID: 202606120001
Revises: 202606050001
Create Date: 2026-06-12
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "202606120001"
down_revision = "202606050001"
branch_labels = None
depends_on = None


def _audit_schema() -> str:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return f"{app_schema}_audit"


def upgrade() -> None:
    audit_schema = _audit_schema()

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("metadata_type", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=128), nullable=True),
        sa.Column("entity_id", sa.String(length=256), nullable=True),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=True),
        sa.Column("correlation_id", sa.String(length=36), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("before_state", sa.String(length=256), nullable=True),
        sa.Column("after_state", sa.String(length=256), nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column(
            "event_timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema=audit_schema,
    )

    op.create_index(
        "ix_audit_events_org_id",
        "audit_events",
        ["organization_id"],
        schema=audit_schema,
    )
    op.create_index(
        "ix_audit_events_entity_id_ts",
        "audit_events",
        ["entity_id", "event_timestamp"],
        schema=audit_schema,
    )
    op.create_index(
        "ix_audit_events_user_id",
        "audit_events",
        ["user_id"],
        schema=audit_schema,
    )
    op.create_index(
        "ix_audit_events_org_type",
        "audit_events",
        ["organization_id", "metadata_type"],
        schema=audit_schema,
    )
    op.create_index(
        "ix_audit_events_event_type",
        "audit_events",
        ["event_type"],
        schema=audit_schema,
    )

    # Partial unique index for idempotency — only when key is set
    op.execute(
        f'CREATE UNIQUE INDEX uq_audit_events_idempotency '
        f'ON "{audit_schema}".audit_events (organization_id, metadata_type, idempotency_key) '
        f'WHERE idempotency_key IS NOT NULL'
    )


def downgrade() -> None:
    audit_schema = _audit_schema()
    op.execute(f'DROP INDEX IF EXISTS "{audit_schema}".uq_audit_events_idempotency')
    op.drop_index("ix_audit_events_event_type", table_name="audit_events", schema=audit_schema)
    op.drop_index("ix_audit_events_org_type", table_name="audit_events", schema=audit_schema)
    op.drop_index("ix_audit_events_user_id", table_name="audit_events", schema=audit_schema)
    op.drop_index("ix_audit_events_entity_id_ts", table_name="audit_events", schema=audit_schema)
    op.drop_index("ix_audit_events_org_id", table_name="audit_events", schema=audit_schema)
    op.drop_table("audit_events", schema=audit_schema)
