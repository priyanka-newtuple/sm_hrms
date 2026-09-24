"""Enable the frontend-recorded timer_duration field type.

The earlier timer migration coupled catalogue enablement to a server-side
runtime table. The timer now writes its final elapsed seconds through the
ordinary entity record path, so only the catalogue mapping is required.

Revision ID: 202608290001
Revises: 202608280001
Create Date: 2026-08-29
"""

from __future__ import annotations

import os

import sqlalchemy as sa

from alembic import op

revision = "202608290001"
down_revision = "202608280001"
branch_labels = None
depends_on = None

FIELD_TYPE_CODE = "timer_duration"
ENGINE_TYPE = "timer_duration"


def _definitions_schema() -> str:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return f"{app_schema}_definitions"


def upgrade() -> None:
    op.execute(
        sa.text(
            f"""
            UPDATE "{_definitions_schema()}".field_type_catalogue
            SET engine_type = :engine_type, is_available = true
            WHERE code = :code
            """
        ).bindparams(engine_type=ENGINE_TYPE, code=FIELD_TYPE_CODE)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            f"""
            UPDATE "{_definitions_schema()}".field_type_catalogue
            SET engine_type = NULL, is_available = false
            WHERE code = :code
            """
        ).bindparams(code=FIELD_TYPE_CODE)
    )
