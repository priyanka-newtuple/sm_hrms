"""Add explicit one-time schedule completion state.

Revision ID: 202607170004
Revises: 202607170003
Create Date: 2026-07-17 00:04:00
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "202607170004"
down_revision = "202607170003"
branch_labels = None
depends_on = None


def _schema() -> str:
    return f"{os.environ.get('POSTGRES_APP_SCHEMA', 'public')}_definitions"


def upgrade() -> None:
    op.add_column(
        "entity_schedules",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        schema=_schema(),
    )


def downgrade() -> None:
    op.drop_column("entity_schedules", "completed_at", schema=_schema())
