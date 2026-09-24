"""Add permissions catalog table.

Revision ID: 202605310001
Revises: 202605290001
Create Date: 2026-05-31
"""

from __future__ import annotations

import os

import sqlalchemy as sa

from alembic import op

revision = "202605310001"
down_revision = "202606010002"
branch_labels = None
depends_on = None

_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")


def upgrade() -> None:
    op.create_table(
        "permissions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("resource", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_permissions")),
        sa.UniqueConstraint("key", name="uq_permissions_key"),
        schema=_schema,
    )
    op.create_index(
        op.f("ix_permissions_key"),
        "permissions",
        ["key"],
        unique=False,
        schema=_schema,
    )
    op.create_index(
        "ix_permissions_resource_action",
        "permissions",
        ["resource", "action"],
        unique=False,
        schema=_schema,
    )
    op.create_index(
        op.f("ix_permissions_resource"),
        "permissions",
        ["resource"],
        unique=False,
        schema=_schema,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_permissions_resource"), table_name="permissions", schema=_schema)
    op.drop_index("ix_permissions_resource_action", table_name="permissions", schema=_schema)
    op.drop_index(op.f("ix_permissions_key"), table_name="permissions", schema=_schema)
    op.drop_table("permissions", schema=_schema)
