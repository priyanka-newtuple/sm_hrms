"""Add permission_key to role_permissions and fix constraints.

Revision ID: 202605310002
Revises: 202605310001
Create Date: 2026-05-31
"""

from __future__ import annotations

import os

import sqlalchemy as sa

from alembic import op

revision = "202605310002"
down_revision = "202605310001"
branch_labels = None
depends_on = None

_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")


def upgrade() -> None:
    # Add permission_key column
    op.add_column(
        "role_permissions",
        sa.Column("permission_key", sa.String(length=128), nullable=True),
        schema=_schema,
    )
    op.create_index(
        "ix_role_permissions_permission_key",
        "role_permissions",
        ["permission_key"],
        unique=False,
        schema=_schema,
    )

    # Make entity_type and action nullable (they are optional for catalog-based permissions)
    op.alter_column("role_permissions", "entity_type", nullable=True, schema=_schema)
    op.alter_column("role_permissions", "action", nullable=True, schema=_schema)

    # Drop old unique constraint on (role_id, entity_type, action)
    op.drop_constraint("uq_role_permissions_unique", "role_permissions", schema=_schema)

    # Add partial unique index for catalog-based permissions: unique by (role_id, permission_key)
    op.execute(
        f'CREATE UNIQUE INDEX uq_role_permissions_key ON "{_schema}".role_permissions (role_id, permission_key) WHERE permission_key IS NOT NULL'
    )

    # Add partial unique index for legacy entity-level permissions: unique by (role_id, entity_type, action)
    op.execute(
        f'CREATE UNIQUE INDEX uq_role_permissions_legacy ON "{_schema}".role_permissions (role_id, entity_type, action) WHERE permission_key IS NULL'
    )


def downgrade() -> None:
    op.execute(f'DROP INDEX IF EXISTS "{_schema}".uq_role_permissions_key')
    op.execute(f'DROP INDEX IF EXISTS "{_schema}".uq_role_permissions_legacy')

    op.alter_column("role_permissions", "entity_type", nullable=False, schema=_schema)
    op.alter_column("role_permissions", "action", nullable=False, schema=_schema)

    op.create_unique_constraint(
        "uq_role_permissions_unique",
        "role_permissions",
        ["role_id", "entity_type", "action"],
        schema=_schema,
    )

    op.drop_index("ix_role_permissions_permission_key", table_name="role_permissions", schema=_schema)
    op.drop_column("role_permissions", "permission_key", schema=_schema)
