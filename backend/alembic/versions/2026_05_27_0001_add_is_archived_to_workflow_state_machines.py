"""Add archived_at column to workflow_state_machines for soft-delete support.

Replaces the unique constraint on (organization_id, machine_name, version) with a
partial unique index that excludes archived rows, so archived workflow names/versions
can be reused.

Revision ID: 202605270001
Revises: 202605230001
Create Date: 2026-05-27
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "202605270001"
down_revision = "202605230001"
branch_labels = None
depends_on = None

_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
_table = "workflow_state_machines"


def upgrade() -> None:
    conn = op.get_bind()

    # Add archived_at column if not present
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

    # Drop old unique constraint if it exists
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE table_schema = :schema AND table_name = :table "
            "AND constraint_name = 'uq_workflow_machine_version'"
        ).bindparams(schema=_schema, table=_table)
    )
    if result.fetchone():
        op.drop_constraint("uq_workflow_machine_version", _table, schema=_schema, type_="unique")

    # Create partial unique index covering only non-archived rows
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_indexes "
            "WHERE schemaname = :schema AND tablename = :table "
            "AND indexname = 'uq_workflow_machine_version_active'"
        ).bindparams(schema=_schema, table=_table)
    )
    if not result.fetchone():
        op.create_index(
            "uq_workflow_machine_version_active",
            _table,
            ["organization_id", "machine_name", "version"],
            unique=True,
            schema=_schema,
            postgresql_where=sa.text("archived_at IS NULL"),
        )

    # Index to keep archived_at IS NULL filters fast at scale
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_indexes "
            "WHERE schemaname = :schema AND tablename = :table "
            "AND indexname = 'ix_workflow_machine_archived_at'"
        ).bindparams(schema=_schema, table=_table)
    )
    if not result.fetchone():
        op.create_index(
            "ix_workflow_machine_archived_at",
            _table,
            ["organization_id", "archived_at"],
            schema=_schema,
        )


def downgrade() -> None:
    op.drop_index("ix_workflow_machine_archived_at", table_name=_table, schema=_schema)
    op.drop_index("uq_workflow_machine_version_active", table_name=_table, schema=_schema)
    op.create_unique_constraint(
        "uq_workflow_machine_version",
        _table,
        ["organization_id", "machine_name", "version"],
        schema=_schema,
    )
    op.drop_column(_table, "archived_at", schema=_schema)
