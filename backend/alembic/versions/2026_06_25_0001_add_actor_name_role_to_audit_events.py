"""Add actor_name and actor_role columns to entity_events.

Stores the display name and role of the actor at the time the event
was recorded. Written at event-emit time so the audit log remains a
point-in-time snapshot even if the user is later renamed or their role
changes.

Revision ID: 202606250001
Revises: 202606240001
Create Date: 2026-06-25
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "202606250001"
down_revision = "202606240001"
branch_labels = None
depends_on = None


def _audit_schema() -> str:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return f"{app_schema}_audit"


def upgrade() -> None:
    audit_schema = _audit_schema()

    op.add_column(
        "entity_events",
        sa.Column("actor_name", sa.String(length=255), nullable=True),
        schema=audit_schema,
    )
    op.add_column(
        "entity_events",
        sa.Column("actor_role", sa.String(length=64), nullable=True),
        schema=audit_schema,
    )


def downgrade() -> None:
    audit_schema = _audit_schema()

    op.drop_column("entity_events", "actor_role", schema=audit_schema)
    op.drop_column("entity_events", "actor_name", schema=audit_schema)
