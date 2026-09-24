"""Refactor picklists table: rename pk->id (UUID primary key), drop user-defined id column, add archived_at for soft-delete.

Revision ID: 202605280001
Revises: 202605270001
Create Date: 2026-05-28
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "202605280001"
down_revision = "202605270001"
branch_labels = None
depends_on = None

_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
_table = "picklists"


def upgrade() -> None:
    conn = op.get_bind()

    # Drop old unique constraint on (organization_id, id) if present
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE table_schema = :schema AND table_name = :table "
            "AND constraint_name = 'uq_picklists_org_id'"
        ).bindparams(schema=_schema, table=_table)
    )
    if result.fetchone():
        op.drop_constraint("uq_picklists_org_id", _table, schema=_schema, type_="unique")

    # Drop old user-defined id column (human-readable slug) before renaming pk -> id
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :table AND column_name = 'id'"
        ).bindparams(schema=_schema, table=_table)
    )
    if result.fetchone():
        op.drop_column(_table, "id", schema=_schema)

    # Rename pk -> id
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :table AND column_name = 'pk'"
        ).bindparams(schema=_schema, table=_table)
    )
    if result.fetchone():
        op.alter_column(_table, "pk", new_column_name="id", schema=_schema)

    # Add archived_at column for soft-delete
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :table AND column_name = 'archived_at'"
        ).bindparams(schema=_schema, table=_table)
    )
    if not result.fetchone():
        op.add_column(
            _table,
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
            schema=_schema,
        )

    # Drop full unique constraint if present (replaced by partial index below)
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE table_schema = :schema AND table_name = :table "
            "AND constraint_name = 'uq_picklists_org_name'"
        ).bindparams(schema=_schema, table=_table)
    )
    if result.fetchone():
        op.drop_constraint("uq_picklists_org_name", _table, schema=_schema, type_="unique")

    # Partial unique index — only enforces uniqueness for non-archived rows
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_indexes "
            "WHERE schemaname = :schema AND tablename = :table "
            "AND indexname = 'uq_picklists_org_name_active'"
        ).bindparams(schema=_schema, table=_table)
    )
    if not result.fetchone():
        op.create_index(
            "uq_picklists_org_name_active",
            _table,
            ["organization_id", "name"],
            unique=True,
            schema=_schema,
            postgresql_where=sa.text("archived_at IS NULL"),
        )


def downgrade() -> None:
    op.drop_index("uq_picklists_org_name_active", table_name=_table, schema=_schema)
    op.drop_column(_table, "archived_at", schema=_schema)
    op.create_unique_constraint(
        "uq_picklists_org_name", _table, ["organization_id", "name"], schema=_schema
    )
    op.add_column(
        _table,
        sa.Column("id", sa.String(128), nullable=True),
        schema=_schema,
    )
    op.create_unique_constraint(
        "uq_picklists_org_id", _table, ["organization_id", "id"], schema=_schema
    )
    op.alter_column(_table, "id", new_column_name="pk", schema=_schema)
