"""Add recurring schedule occurrence batch size.

Revision ID: 202607170002
Revises: 202607170001
Create Date: 2026-07-17 00:02:00
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "202607170002"
down_revision = "202607170001"
branch_labels = None
depends_on = None


def _definitions_schema() -> str:
    return f"{os.environ.get('POSTGRES_APP_SCHEMA', 'public')}_definitions"


def upgrade() -> None:
    op.add_column(
        "entity_schedules",
        sa.Column(
            "occurrences_per_batch",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        schema=_definitions_schema(),
    )


def downgrade() -> None:
    op.drop_column(
        "entity_schedules",
        "occurrences_per_batch",
        schema=_definitions_schema(),
    )
