"""Add definitions schema and entity_types table.

Introduces the canonical entity_types registry as the first table in the
state-machine rewrite. Schema is derived from POSTGRES_APP_SCHEMA so
multiple environments sharing one database stay isolated.

Revision ID: 202605020004
Revises: 202604270003
Create Date: 2026-05-02 00:04:00
"""

from __future__ import annotations

import os

from alembic import op
import sqlalchemy as sa


revision = "202605020004"
down_revision = "202604270003"
branch_labels = None
depends_on = None


def _schemas() -> tuple[str, str]:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    definitions_schema = f"{app_schema}_definitions"
    return app_schema, definitions_schema


def upgrade() -> None:
    app_schema, definitions_schema = _schemas()

    op.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{definitions_schema}"'))

    op.create_table(
        "entity_types",
        sa.Column("entity_type_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("schema", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
        sa.ForeignKeyConstraint(
            ["organization_id"],
            [f"{app_schema}.organizations.id"],
            ondelete="CASCADE",
            name="fk_entity_types_organization_id",
        ),
        sa.PrimaryKeyConstraint("entity_type_id", name="pk_entity_types"),
        sa.UniqueConstraint(
            "organization_id",
            "name",
            "version",
            name="uq_entity_types_org_name_version",
        ),
        schema=definitions_schema,
    )

    op.create_index(
        "ix_entity_types_organization_id",
        "entity_types",
        ["organization_id"],
        schema=definitions_schema,
    )
    op.create_index(
        "ix_entity_types_org_name_active",
        "entity_types",
        ["organization_id", "name", "is_active"],
        schema=definitions_schema,
    )


def downgrade() -> None:
    _, definitions_schema = _schemas()

    op.drop_index(
        "ix_entity_types_org_name_active",
        table_name="entity_types",
        schema=definitions_schema,
    )
    op.drop_index(
        "ix_entity_types_organization_id",
        table_name="entity_types",
        schema=definitions_schema,
    )
    op.drop_table("entity_types", schema=definitions_schema)
    op.execute(sa.text(f'DROP SCHEMA IF EXISTS "{definitions_schema}" CASCADE'))
