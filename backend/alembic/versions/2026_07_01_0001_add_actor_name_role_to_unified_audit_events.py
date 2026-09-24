"""Add actor_name and actor_role columns to audit_events.

Stores the display name and role of the actor at the time the event
was recorded. Written at event-emit time so the audit log remains a
point-in-time snapshot even if the user is later renamed or their role
changes. Entity CRUD now writes exclusively to this unified table (see
entities/manager.py `_try_emit_audit_event`), replacing the dedicated
entity_events table as the write target.

Revision ID: 202607010001
Revises: 202606270001
Create Date: 2026-07-01
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "202607010001"
down_revision = "202606270001"
branch_labels = None
depends_on = None


def _audit_schema() -> str:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return f"{app_schema}_audit"


def upgrade() -> None:
    audit_schema = _audit_schema()

    op.add_column(
        "audit_events",
        sa.Column("actor_name", sa.String(length=255), nullable=True),
        schema=audit_schema,
    )
    op.add_column(
        "audit_events",
        sa.Column("actor_role", sa.String(length=64), nullable=True),
        schema=audit_schema,
    )


def downgrade() -> None:
    audit_schema = _audit_schema()

    op.drop_column("audit_events", "actor_role", schema=audit_schema)
    op.drop_column("audit_events", "actor_name", schema=audit_schema)
