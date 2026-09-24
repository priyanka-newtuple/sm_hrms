"""Add inherit_from to method_library_method_version_fields.

Per-usage flag naming a source entity type + field this Method-field's value
should come from at pin time, e.g. "Client.name". Lives on the link row (not
the Field Library field itself) so the same reusable field can be entered
directly in one Method and inherited in another.

Revision ID: 202608280001
Revises: 202608250003
Create Date: 2026-08-28
"""

from __future__ import annotations

import os

import sqlalchemy as sa

from alembic import op

revision = "202608280001"
down_revision = "202608250003"
branch_labels = None
depends_on = None

TABLE_NAME = "method_library_method_version_fields"
COLUMN_NAME = "inherit_from"


def _definitions_schema() -> str:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return f"{app_schema}_definitions"


def upgrade() -> None:
    op.add_column(
        TABLE_NAME,
        sa.Column(COLUMN_NAME, sa.String(length=300), nullable=True),
        schema=_definitions_schema(),
    )


def downgrade() -> None:
    op.drop_column(TABLE_NAME, COLUMN_NAME, schema=_definitions_schema())
