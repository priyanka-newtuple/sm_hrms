"""Add canvas_metadata_json to workflow_state_machines.

Stores per-workflow canvas layout (node positions and future UI metadata)
as a nullable JSON column. Separate from definition_json so position
updates never touch workflow logic or trigger re-validation.

Revision ID: 202605060001
Revises: 202605050002
Create Date: 2026-05-06
"""

from __future__ import annotations

import os

from alembic import op
import sqlalchemy as sa


revision = "202605060001"
down_revision = "202605050002"
branch_labels = None
depends_on = None


def _app_schema() -> str:
    return os.environ.get("POSTGRES_APP_SCHEMA", "public")


def upgrade() -> None:
    app_schema = _app_schema()
    op.add_column(
        "workflow_state_machines",
        sa.Column("canvas_metadata_json", sa.JSON(), nullable=True),
        schema=app_schema,
    )


def downgrade() -> None:
    app_schema = _app_schema()
    op.drop_column("workflow_state_machines", "canvas_metadata_json", schema=app_schema)
