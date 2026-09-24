"""Add display_order column to entity_type_schema.

Forms attached to the same entity type render as ordered tabs; this column
controls that order (lower shows first). Defaults to 0 so existing rows keep
their previous schema_key-based ordering as a tiebreaker.

Revision ID: 202606040002
Revises: 202606040001
Create Date: 2026-06-04
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "202606040002"
down_revision = "202606040001"
branch_labels = None
depends_on = None

_definitions_schema = f"{os.environ.get('POSTGRES_APP_SCHEMA', 'public')}_definitions"
_table = "entity_type_schema"


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :table "
            "AND column_name = 'display_order'"
        ).bindparams(schema=_definitions_schema, table=_table)
    )
    if not result.fetchone():
        op.add_column(
            _table,
            sa.Column(
                "display_order",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            schema=_definitions_schema,
        )


def downgrade() -> None:
    op.drop_column(_table, "display_order", schema=_definitions_schema)
