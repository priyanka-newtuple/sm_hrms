"""Add actor_name column to transition_attempts.

Stores the display name of the actor at the time the transition was
attempted. Written at record time so the audit log remains a
point-in-time snapshot even if the user is later renamed.

Revision ID: 202606260001
Revises: 202606250001
Create Date: 2026-06-26
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "202606260001"
down_revision = "202606250001"
branch_labels = None
depends_on = None


def _audit_schema() -> str:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return f"{app_schema}_audit"


def upgrade() -> None:
    audit_schema = _audit_schema()
    op.add_column(
        "transition_attempts",
        sa.Column("actor_name", sa.String(length=255), nullable=True),
        schema=audit_schema,
    )


def downgrade() -> None:
    audit_schema = _audit_schema()
    op.drop_column("transition_attempts", "actor_name", schema=audit_schema)
