"""Enable Document in the Field Library catalogue.

Revision ID: 202608250003
Revises: 202608270001
Create Date: 2026-08-25
"""

from __future__ import annotations

import os

import sqlalchemy as sa

from alembic import op

revision = "202608250003"
down_revision = "202608270001"
branch_labels = None
depends_on = None


def _definitions_schema() -> str:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return f"{app_schema}_definitions"


def upgrade() -> None:
    definitions_schema = _definitions_schema()
    op.get_bind().execute(
        sa.text(
            f"""
            UPDATE "{definitions_schema}".field_type_catalogue
            SET engine_type = 'document',
                is_available = true,
                updated_at = now()
            WHERE code = 'document'
            """
        )
    )


def downgrade() -> None:
    definitions_schema = _definitions_schema()
    op.get_bind().execute(
        sa.text(
            f"""
            UPDATE "{definitions_schema}".field_type_catalogue
            SET engine_type = NULL,
                is_available = false,
                updated_at = now()
            WHERE code = 'document'
            """
        )
    )
