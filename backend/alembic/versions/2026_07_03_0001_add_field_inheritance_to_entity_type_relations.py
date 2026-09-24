"""Add field-inheritance columns to definitions.entity_type_relations.

Adds relation_type/relation_metadata/updated_at/deleted_at so a relation
declaration between two entity types can drive REFERENCE/SNAPSHOT field
inheritance. relation_name is made nullable. The old per-name uniqueness
is replaced by a single-active-declaration-per-type-pair partial index.

Revision ID: 202607030001
Revises: 202606300001
Create Date: 2026-07-03
"""

from __future__ import annotations

import os

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "202607030001"
down_revision = "202606300001"
branch_labels = None
depends_on = None


def _definitions_schema() -> str:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return f"{app_schema}_definitions"


def upgrade() -> None:
    definitions_schema = _definitions_schema()

    op.add_column(
        "entity_type_relations",
        sa.Column(
            "relation_type",
            sa.String(length=32),
            nullable=False,
            server_default="SNAPSHOT",
        ),
        schema=definitions_schema,
    )
    op.add_column(
        "entity_type_relations",
        sa.Column(
            "relation_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        schema=definitions_schema,
    )
    op.add_column(
        "entity_type_relations",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema=definitions_schema,
    )
    op.add_column(
        "entity_type_relations",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        schema=definitions_schema,
    )

    op.alter_column(
        "entity_type_relations",
        "relation_name",
        existing_type=sa.String(length=128),
        nullable=True,
        schema=definitions_schema,
    )

    op.drop_constraint(
        "uq_entity_type_relations_org_from_to_name",
        "entity_type_relations",
        schema=definitions_schema,
        type_="unique",
    )

    op.create_index(
        "uq_entity_type_relations_active_org_from_to",
        "entity_type_relations",
        ["organization_id", "from_entity_type_id", "to_entity_type_id"],
        unique=True,
        schema=definitions_schema,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    definitions_schema = _definitions_schema()

    op.drop_index(
        "uq_entity_type_relations_active_org_from_to",
        table_name="entity_type_relations",
        schema=definitions_schema,
    )

    op.create_unique_constraint(
        "uq_entity_type_relations_org_from_to_name",
        "entity_type_relations",
        ["organization_id", "from_entity_type_id", "to_entity_type_id", "relation_name"],
        schema=definitions_schema,
    )

    op.alter_column(
        "entity_type_relations",
        "relation_name",
        existing_type=sa.String(length=128),
        nullable=False,
        schema=definitions_schema,
    )

    op.drop_column("entity_type_relations", "deleted_at", schema=definitions_schema)
    op.drop_column("entity_type_relations", "updated_at", schema=definitions_schema)
    op.drop_column("entity_type_relations", "relation_metadata", schema=definitions_schema)
    op.drop_column("entity_type_relations", "relation_type", schema=definitions_schema)
