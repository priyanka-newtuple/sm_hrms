"""Replace connectors.entity_type with entity_types (JSONB list).

A connector can now apply to several entity types. Existing single-type rows
are backfilled to a one-item list, then the legacy `entity_type` column and
its indexes are dropped.

Revision ID: 202607090001
Revises: 202607080001
Create Date: 2026-07-09
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "202607090001"
down_revision = "202607080001"
branch_labels = None
depends_on = None

_app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "modular_backend")


def upgrade() -> None:
    op.add_column(
        "connectors",
        sa.Column("entity_types", JSONB(), nullable=True),
        schema=_app_schema,
    )
    op.execute(
        f"""
        UPDATE "{_app_schema}".connectors
        SET entity_types = jsonb_build_array(entity_type)
        WHERE entity_type IS NOT NULL
        """
    )
    op.drop_index("ix_connectors_org_entity_type", table_name="connectors", schema=_app_schema)
    op.drop_index("ix_connectors_entity_type", table_name="connectors", schema=_app_schema)
    op.drop_column("connectors", "entity_type", schema=_app_schema)


def downgrade() -> None:
    op.add_column(
        "connectors",
        sa.Column("entity_type", sa.String(128), nullable=True),
        schema=_app_schema,
    )
    op.execute(
        f"""
        UPDATE "{_app_schema}".connectors
        SET entity_type = entity_types ->> 0
        WHERE entity_types IS NOT NULL AND jsonb_array_length(entity_types) > 0
        """
    )
    op.create_index(
        "ix_connectors_entity_type", "connectors", ["entity_type"], schema=_app_schema
    )
    op.create_index(
        "ix_connectors_org_entity_type",
        "connectors",
        ["organization_id", "entity_type"],
        schema=_app_schema,
    )
    op.drop_column("connectors", "entity_types", schema=_app_schema)
