"""Add first-class due date to runtime entities.

Revision ID: 202607140001
Revises: 202607100002
Create Date: 2026-07-14 00:01:00
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "202607140001"
down_revision = "202607100002"
branch_labels = None
depends_on = None


def _runtime_schema() -> str:
    return f"{os.environ.get('POSTGRES_APP_SCHEMA', 'public')}_runtime"


def upgrade() -> None:
    op.add_column(
        "entities",
        sa.Column("due_date", sa.Date(), nullable=True),
        schema=_runtime_schema(),
    )


def downgrade() -> None:
    op.drop_column("entities", "due_date", schema=_runtime_schema())
