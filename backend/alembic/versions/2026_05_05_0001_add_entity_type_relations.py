"""Add definitions.entity_type_relations table.

Stores allowed directed relations between entity types inside the
definitions schema so runtime entity graph edges can be validated against
organization-scoped metadata.

Revision ID: 202605050001
Revises: 202605040002
Create Date: 2026-05-05
"""

from __future__ import annotations

import os

from alembic import op
import sqlalchemy as sa


revision = "202605050001"
down_revision = "202605040002"
branch_labels = None
depends_on = None


def _schemas() -> tuple[str, str]:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return app_schema, f"{app_schema}_definitions"


def upgrade() -> None:
    app_schema, definitions_schema = _schemas()

    op.create_table(
        "entity_type_relations",
        sa.Column("relation_def_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("from_entity_type_id", sa.String(length=36), nullable=False),
        sa.Column("to_entity_type_id", sa.String(length=36), nullable=False),
        sa.Column("relation_name", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            [f"{app_schema}.organizations.id"],
            ondelete="CASCADE",
            name="fk_entity_type_relations_organization_id",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "from_entity_type_id"],
            [
                f"{definitions_schema}.entity_types.organization_id",
                f"{definitions_schema}.entity_types.entity_type_id",
            ],
            ondelete="CASCADE",
            name="fk_entity_type_relations_org_from_entity_type_id",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "to_entity_type_id"],
            [
                f"{definitions_schema}.entity_types.organization_id",
                f"{definitions_schema}.entity_types.entity_type_id",
            ],
            ondelete="CASCADE",
            name="fk_entity_type_relations_org_to_entity_type_id",
        ),
        sa.PrimaryKeyConstraint("relation_def_id", name="pk_entity_type_relations"),
        sa.UniqueConstraint(
            "organization_id",
            "from_entity_type_id",
            "to_entity_type_id",
            "relation_name",
            name="uq_entity_type_relations_org_from_to_name",
        ),
        schema=definitions_schema,
    )

    op.create_index(
        "ix_entity_type_relations_org_from",
        "entity_type_relations",
        ["organization_id", "from_entity_type_id"],
        schema=definitions_schema,
    )


def downgrade() -> None:
    _, definitions_schema = _schemas()

    op.drop_index(
        "ix_entity_type_relations_org_from",
        table_name="entity_type_relations",
        schema=definitions_schema,
    )
    op.drop_table("entity_type_relations", schema=definitions_schema)
