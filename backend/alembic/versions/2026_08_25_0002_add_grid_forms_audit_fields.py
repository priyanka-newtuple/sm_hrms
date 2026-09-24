"""Add last_edited_by/last_edited_fields audit columns to grid form tables.

Revision ID: 202608250002
Revises: 202608250001
Create Date: 2026-07-19 00:01:00
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "202608250002"
down_revision = "202608250001"
branch_labels = None
depends_on = None


def _definitions_schema() -> str:
    return f"{os.environ.get('POSTGRES_APP_SCHEMA', 'public')}_definitions"


def _runtime_schema() -> str:
    return f"{os.environ.get('POSTGRES_APP_SCHEMA', 'public')}_runtime"


def upgrade() -> None:
    op.add_column(
        "grid_form_templates",
        sa.Column("last_edited_by", sa.String(128), nullable=True),
        schema=_definitions_schema(),
    )
    op.add_column(
        "grid_form_templates",
        sa.Column(
            "last_edited_fields", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        schema=_definitions_schema(),
    )
    op.add_column(
        "grid_form_instances",
        sa.Column("last_edited_by", sa.String(128), nullable=True),
        schema=_runtime_schema(),
    )
    op.add_column(
        "grid_form_instances",
        sa.Column(
            "last_edited_fields", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        schema=_runtime_schema(),
    )


def downgrade() -> None:
    op.drop_column("grid_form_instances", "last_edited_fields", schema=_runtime_schema())
    op.drop_column("grid_form_instances", "last_edited_by", schema=_runtime_schema())
    op.drop_column("grid_form_templates", "last_edited_fields", schema=_definitions_schema())
    op.drop_column("grid_form_templates", "last_edited_by", schema=_definitions_schema())
