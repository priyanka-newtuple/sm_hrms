"""Add transition_permissions table for per-role transition allow-lists.

Revision ID: 202606050001
Revises: 202606040002
Create Date: 2026-06-05
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "202606050001"
down_revision = "202606040002"
branch_labels = None
depends_on = None

_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")


def upgrade() -> None:
    op.create_table(
        "transition_permissions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("role_id", sa.String(length=36), nullable=False),
        sa.Column("machine_name", sa.String(length=128), nullable=False),
        sa.Column("transition_key", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], [f"{_schema}.roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transition_permissions")),
        sa.UniqueConstraint("role_id", "machine_name", "transition_key", name="uq_transition_permissions_unique"),
        schema=_schema,
    )
    op.create_index(
        "ix_transition_permissions_role_id",
        "transition_permissions",
        ["role_id"],
        unique=False,
        schema=_schema,
    )


def downgrade() -> None:
    op.drop_index("ix_transition_permissions_role_id", table_name="transition_permissions", schema=_schema)
    op.drop_table("transition_permissions", schema=_schema)
