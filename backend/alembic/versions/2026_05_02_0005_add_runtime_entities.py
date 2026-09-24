"""Add runtime schema and entities table.

Second slice of the state-machine rewrite. Introduces the canonical
entity instance table (data, identity, owner) separate from any state
machine enrollment. Schema is derived from POSTGRES_APP_SCHEMA.

Revision ID: 202605020005
Revises: 202605020004
Create Date: 2026-05-02 00:05:00
"""

from __future__ import annotations

import os

from alembic import op
import sqlalchemy as sa


revision = "202605020005"
down_revision = "202605020004"
branch_labels = None
depends_on = None


def _schemas() -> tuple[str, str, str]:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    definitions_schema = f"{app_schema}_definitions"
    runtime_schema = f"{app_schema}_runtime"
    return app_schema, definitions_schema, runtime_schema


def upgrade() -> None:
    app_schema, definitions_schema, runtime_schema = _schemas()

    op.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{runtime_schema}"'))

    op.create_table(
        "entities",
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("entity_type_id", sa.String(length=36), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("owner_id", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            [f"{app_schema}.organizations.id"],
            ondelete="CASCADE",
            name="fk_entities_organization_id",
        ),
        sa.ForeignKeyConstraint(
            ["entity_type_id"],
            [f"{definitions_schema}.entity_types.entity_type_id"],
            ondelete="RESTRICT",
            name="fk_entities_entity_type_id",
        ),
        sa.PrimaryKeyConstraint("entity_id", name="pk_entities"),
        schema=runtime_schema,
    )

    op.create_index(
        "ix_entities_organization_id",
        "entities",
        ["organization_id"],
        schema=runtime_schema,
    )
    op.create_index(
        "ix_entities_entity_type_id",
        "entities",
        ["entity_type_id"],
        schema=runtime_schema,
    )
    op.create_index(
        "ix_entities_org_type_active",
        "entities",
        ["organization_id", "entity_type_id", "archived_at"],
        schema=runtime_schema,
    )


def downgrade() -> None:
    _, _, runtime_schema = _schemas()

    op.drop_index("ix_entities_org_type_active", table_name="entities", schema=runtime_schema)
    op.drop_index("ix_entities_entity_type_id", table_name="entities", schema=runtime_schema)
    op.drop_index("ix_entities_organization_id", table_name="entities", schema=runtime_schema)
    op.drop_table("entities", schema=runtime_schema)
    op.execute(sa.text(f'DROP SCHEMA IF EXISTS "{runtime_schema}" CASCADE'))
