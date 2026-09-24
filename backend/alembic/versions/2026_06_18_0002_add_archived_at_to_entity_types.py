"""Add archived_at to entity_types and fix unique constraint to allow re-creation after soft-delete.

Replaces the full-table unique constraint on (org, name, version) with a partial
unique index that only applies to active rows (is_active = TRUE). This allows
unlimited soft-delete / recreate cycles for the same entity type name.

Revision ID: 202606180002
Revises: 202606150001
Create Date: 2026-06-18
"""

from __future__ import annotations

import os

import sqlalchemy as sa

from alembic import op

revision = "202606180002"
down_revision = "202606180001"
branch_labels = None
depends_on = None

_app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "modular_backend")
_definitions_schema = f"{_app_schema}_definitions"


def upgrade() -> None:
    op.add_column(
        "entity_types",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        schema=_definitions_schema,
    )
    op.drop_constraint(
        "uq_entity_types_org_name_version",
        "entity_types",
        schema=_definitions_schema,
    )
    # Partial unique index — only active rows are constrained to be unique.
    # Soft-deleted rows (is_active = FALSE) are excluded, so the same name
    # can be deleted and recreated any number of times.
    op.execute(
        f"""
        CREATE UNIQUE INDEX uq_entity_types_org_name_version_active
        ON {_definitions_schema}.entity_types (organization_id, name, version)
        WHERE is_active = TRUE
        """
    )


def downgrade() -> None:
    op.execute(
        f"DROP INDEX IF EXISTS {_definitions_schema}.uq_entity_types_org_name_version_active"
    )
    op.create_unique_constraint(
        "uq_entity_types_org_name_version",
        "entity_types",
        ["organization_id", "name", "version"],
        schema=_definitions_schema,
    )
    op.drop_column("entity_types", "archived_at", schema=_definitions_schema)
