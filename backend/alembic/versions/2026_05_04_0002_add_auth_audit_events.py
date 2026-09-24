"""Add audit.auth_events table for the auth audit log.

The auth audit log was previously co-located with the legacy
`<app_schema>.entity_events` table (the same table the workflow runtime
used). Wave 1 cut the workflow runtime over to `<app_schema>_audit.entity_events`,
which has a composite FK to `runtime.entities` so synthetic auth entity
ids cannot live there. This migration adds a dedicated, FK-free
`<app_schema>_audit.auth_events` table for login / logout / token /
permission events.

Auth keeps writing to the legacy table on the way in; the next commit
flips the writer to the new one. Once that ships and the legacy log
soaks for a release we can drop the legacy `entity_events` table.

Revision ID: 202605040002
Revises: 202605040001
Create Date: 2026-05-04
"""

from __future__ import annotations

import os

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "202605040002"
down_revision = "202605040001"
branch_labels = None
depends_on = None


def _schemas() -> tuple[str, str]:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return app_schema, f"{app_schema}_audit"


def upgrade() -> None:
    app_schema, audit_schema = _schemas()

    op.create_table(
        "auth_events",
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=True),
        sa.Column("correlation_id", sa.String(length=36), nullable=True),
        sa.Column("payload", JSONB, nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            [f"{app_schema}.organizations.id"],
            ondelete="CASCADE",
            name="fk_auth_events_organization_id",
        ),
        sa.PrimaryKeyConstraint("event_id", name="pk_auth_events"),
        schema=audit_schema,
    )
    op.create_index(
        "ix_audit_auth_events_organization_id",
        "auth_events",
        ["organization_id"],
        schema=audit_schema,
    )
    op.create_index(
        "ix_audit_auth_events_event_type",
        "auth_events",
        ["event_type"],
        schema=audit_schema,
    )
    op.create_index(
        "ix_audit_auth_events_user_id",
        "auth_events",
        ["user_id"],
        schema=audit_schema,
    )
    op.create_index(
        "ix_audit_auth_events_email_lower",
        "auth_events",
        [sa.text("lower(email)")],
        schema=audit_schema,
    )
    op.create_index(
        "ix_audit_auth_events_org_occurred",
        "auth_events",
        ["organization_id", "occurred_at"],
        schema=audit_schema,
    )


def downgrade() -> None:
    _, audit_schema = _schemas()
    op.drop_index("ix_audit_auth_events_org_occurred", table_name="auth_events", schema=audit_schema)
    op.drop_index("ix_audit_auth_events_email_lower", table_name="auth_events", schema=audit_schema)
    op.drop_index("ix_audit_auth_events_user_id", table_name="auth_events", schema=audit_schema)
    op.drop_index("ix_audit_auth_events_event_type", table_name="auth_events", schema=audit_schema)
    op.drop_index("ix_audit_auth_events_organization_id", table_name="auth_events", schema=audit_schema)
    op.drop_table("auth_events", schema=audit_schema)
