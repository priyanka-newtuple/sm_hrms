"""Add read-condition columns to role_permissions (entity field permission filter).

Revision ID: 202607150004
Revises: 202607150003
Create Date: 2026-07-15 00:03:00
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "202607150004"
down_revision = "202607150003"
branch_labels = None
depends_on = None

_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")


def upgrade() -> None:
    op.add_column(
        "role_permissions",
        sa.Column("entity_field", sa.String(length=128), nullable=True),
        schema=_schema,
    )
    op.add_column(
        "role_permissions",
        sa.Column("operator", sa.String(length=32), nullable=True),
        schema=_schema,
    )
    op.add_column(
        "role_permissions",
        sa.Column("value_source", sa.String(length=32), nullable=True),
        schema=_schema,
    )
    op.add_column(
        "role_permissions",
        sa.Column("condition_value", sa.String(length=256), nullable=True),
        schema=_schema,
    )


def downgrade() -> None:
    op.drop_column("role_permissions", "condition_value", schema=_schema)
    op.drop_column("role_permissions", "value_source", schema=_schema)
    op.drop_column("role_permissions", "operator", schema=_schema)
    op.drop_column("role_permissions", "entity_field", schema=_schema)
