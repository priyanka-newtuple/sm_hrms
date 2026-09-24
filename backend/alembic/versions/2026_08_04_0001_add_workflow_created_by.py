"""Add created_by to workflow_state_machines.

Revision ID: 202608040001
Revises: 202608030001
Create Date: 2026-08-04
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "202608040001"
down_revision = "202608030001"
branch_labels = None
depends_on = None

_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")


def upgrade() -> None:
    op.add_column(
        "workflow_state_machines",
        sa.Column("created_by", sa.String(length=36), nullable=True),
        schema=_schema,
    )


def downgrade() -> None:
    op.drop_column("workflow_state_machines", "created_by", schema=_schema)
