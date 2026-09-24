"""Add source_entity_type/source_field_key to method version fields.

Revision ID: 202608300001
Revises: 202608290001
Create Date: 2026-08-30 00:01:00
"""

from __future__ import annotations

import os

import sqlalchemy as sa

from alembic import op

revision = "202608300001"
down_revision = "202608290001"
branch_labels = None
depends_on = None


def _definitions_schema() -> str:
    return f"{os.environ.get('POSTGRES_APP_SCHEMA', 'public')}_definitions"


def upgrade() -> None:
    op.add_column(
        "method_library_method_version_fields",
        sa.Column("source_entity_type", sa.String(256), nullable=True),
        schema=_definitions_schema(),
    )
    op.add_column(
        "method_library_method_version_fields",
        sa.Column("source_field_key", sa.String(256), nullable=True),
        schema=_definitions_schema(),
    )


def downgrade() -> None:
    op.drop_column(
        "method_library_method_version_fields", "source_field_key", schema=_definitions_schema()
    )
    op.drop_column(
        "method_library_method_version_fields", "source_entity_type", schema=_definitions_schema()
    )
