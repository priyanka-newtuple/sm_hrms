"""Add archived_at column to roles for soft delete.

Revision ID: 202606040001
Revises: 202606010002
Create Date: 2026-06-04
"""

from __future__ import annotations

import os

import sqlalchemy as sa

from alembic import op

revision = "202606040001"
down_revision = "202605310002"
branch_labels = None
depends_on = None

_schema = os.environ.get("POSTGRES_APP_SCHEMA", "modular_backend")


def upgrade() -> None:
    op.add_column(
        "roles",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        schema=_schema,
    )


def downgrade() -> None:
    op.drop_column("roles", "archived_at", schema=_schema)
