"""Add per-role workflow allow-lists.

Revision ID: 202607260001
Revises: 202607190001
Create Date: 2026-07-26
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "202607260001"
down_revision = "202607190001"
branch_labels = None
depends_on = None

_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")


def upgrade() -> None:
    op.create_table(
        "role_workflow_permissions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("role_id", sa.String(length=36), nullable=False),
        sa.Column("machine_name", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], [f"{_schema}.roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_role_workflow_permissions")),
        sa.UniqueConstraint("role_id", "machine_name", name="uq_role_workflow_permissions_unique"),
        schema=_schema,
    )
    op.create_index(
        "ix_role_workflow_permissions_role_id",
        "role_workflow_permissions",
        ["role_id"],
        unique=False,
        schema=_schema,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_role_workflow_permissions_role_id",
        table_name="role_workflow_permissions",
        schema=_schema,
    )
    op.drop_table("role_workflow_permissions", schema=_schema)
