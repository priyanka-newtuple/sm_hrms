"""Add assignee_id to runtime entities.

Adds an optional `assignee_id` column to the runtime entities table so an
entity can be assigned to an organization user (distinct from `owner_id`).
Assigning an entity to a user emits an in-app "assignment" notification.

Revision ID: 202606180001
Revises: 202606120001
Create Date: 2026-06-18 00:01:00
"""

from __future__ import annotations

import os

from alembic import op
import sqlalchemy as sa


revision = "202606180001"
down_revision = "202606150001"
branch_labels = None
depends_on = None


def _runtime_schema() -> str:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return f"{app_schema}_runtime"


def upgrade() -> None:
    op.add_column(
        "entities",
        sa.Column("assignee_id", sa.String(length=128), nullable=True),
        schema=_runtime_schema(),
    )


def downgrade() -> None:
    op.drop_column("entities", "assignee_id", schema=_runtime_schema())
