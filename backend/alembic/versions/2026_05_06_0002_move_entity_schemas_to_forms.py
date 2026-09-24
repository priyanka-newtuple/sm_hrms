"""Create forms-owned entity_type_schema table and backfill workflow schemas.

This migration moves reusable entity form schemas out of the workflow module's
legacy `workflow_entity_schema_picklists` table into the definitions schema so
forms owns CRUD and workflow can consume the same schema metadata.

Upgrade steps:
- create `<app_schema>_definitions.entity_type_schema`
- copy all rows from `<app_schema>.workflow_entity_schema_picklists`
- drop the legacy workflow table and its indexes

Downgrade performs the reverse copy back into the workflow table before
dropping the forms-owned table.

Revision ID: 202605060002
Revises: 202605060001
Create Date: 2026-05-06
"""

from __future__ import annotations

import os

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "202605060002"
down_revision = "202605060001"
branch_labels = None
depends_on = None


def _schemas() -> tuple[str, str]:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return app_schema, f"{app_schema}_definitions"


def upgrade() -> None:
    app_schema, definitions_schema = _schemas()

    op.create_table(
        "entity_type_schema",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("schema_key", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("entity_type", sa.String(length=128), nullable=False),
        sa.Column("fields_json", JSONB, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_entity_type_schema"),
        sa.UniqueConstraint("organization_id", "schema_key", name="uq_entity_type_schema_org_schema_key"),
        schema=definitions_schema,
    )
    op.create_index(
        "ix_entity_type_schema_organization_id",
        "entity_type_schema",
        ["organization_id"],
        unique=False,
        schema=definitions_schema,
    )
    op.create_index(
        "ix_entity_type_schema_schema_key",
        "entity_type_schema",
        ["schema_key"],
        unique=False,
        schema=definitions_schema,
    )
    op.create_index(
        "ix_entity_type_schema_entity_type",
        "entity_type_schema",
        ["entity_type"],
        unique=False,
        schema=definitions_schema,
    )
    op.create_index(
        "ix_entity_type_schema_content_hash",
        "entity_type_schema",
        ["content_hash"],
        unique=False,
        schema=definitions_schema,
    )
    op.create_index(
        "ix_entity_type_schema_lookup",
        "entity_type_schema",
        ["organization_id", "schema_key", "is_active"],
        unique=False,
        schema=definitions_schema,
    )

    op.execute(
        sa.text(
            f"""
            INSERT INTO "{definitions_schema}".entity_type_schema (
                id,
                organization_id,
                schema_key,
                name,
                description,
                entity_type,
                fields_json,
                is_active,
                content_hash,
                created_at,
                updated_at
            )
            SELECT
                id,
                organization_id,
                schema_key,
                name,
                description,
                entity_type,
                fields_json::jsonb,
                is_active,
                content_hash,
                created_at,
                updated_at
            FROM "{app_schema}".workflow_entity_schema_picklists
            """
        )
    )

    op.drop_index(
        "ix_workflow_schema_picklist_lookup",
        table_name="workflow_entity_schema_picklists",
        schema=app_schema,
    )
    op.drop_index(
        "ix_workflow_entity_schema_picklists_content_hash",
        table_name="workflow_entity_schema_picklists",
        schema=app_schema,
    )
    op.drop_index(
        "ix_workflow_entity_schema_picklists_entity_type",
        table_name="workflow_entity_schema_picklists",
        schema=app_schema,
    )
    op.drop_index(
        "ix_workflow_entity_schema_picklists_schema_key",
        table_name="workflow_entity_schema_picklists",
        schema=app_schema,
    )
    op.drop_index(
        "ix_workflow_entity_schema_picklists_organization_id",
        table_name="workflow_entity_schema_picklists",
        schema=app_schema,
    )
    op.drop_table("workflow_entity_schema_picklists", schema=app_schema)


def downgrade() -> None:
    app_schema, definitions_schema = _schemas()

    op.create_table(
        "workflow_entity_schema_picklists",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("schema_key", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("entity_type", sa.String(length=128), nullable=False),
        sa.Column("fields_json", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_workflow_entity_schema_picklists"),
        sa.UniqueConstraint("organization_id", "schema_key", name="uq_workflow_schema_picklist"),
        schema=app_schema,
    )
    op.create_index(
        "ix_workflow_entity_schema_picklists_organization_id",
        "workflow_entity_schema_picklists",
        ["organization_id"],
        unique=False,
        schema=app_schema,
    )
    op.create_index(
        "ix_workflow_entity_schema_picklists_schema_key",
        "workflow_entity_schema_picklists",
        ["schema_key"],
        unique=False,
        schema=app_schema,
    )
    op.create_index(
        "ix_workflow_entity_schema_picklists_entity_type",
        "workflow_entity_schema_picklists",
        ["entity_type"],
        unique=False,
        schema=app_schema,
    )
    op.create_index(
        "ix_workflow_entity_schema_picklists_content_hash",
        "workflow_entity_schema_picklists",
        ["content_hash"],
        unique=False,
        schema=app_schema,
    )
    op.create_index(
        "ix_workflow_schema_picklist_lookup",
        "workflow_entity_schema_picklists",
        ["organization_id", "schema_key", "is_active"],
        unique=False,
        schema=app_schema,
    )

    op.execute(
        sa.text(
            f"""
            INSERT INTO "{app_schema}".workflow_entity_schema_picklists (
                id,
                organization_id,
                schema_key,
                name,
                description,
                entity_type,
                fields_json,
                is_active,
                content_hash,
                created_at,
                updated_at
            )
            SELECT
                id,
                organization_id,
                schema_key,
                name,
                description,
                entity_type,
                fields_json,
                is_active,
                content_hash,
                created_at,
                updated_at
            FROM "{definitions_schema}".entity_type_schema
            """
        )
    )

    op.drop_index("ix_entity_type_schema_lookup", table_name="entity_type_schema", schema=definitions_schema)
    op.drop_index("ix_entity_type_schema_content_hash", table_name="entity_type_schema", schema=definitions_schema)
    op.drop_index("ix_entity_type_schema_entity_type", table_name="entity_type_schema", schema=definitions_schema)
    op.drop_index("ix_entity_type_schema_schema_key", table_name="entity_type_schema", schema=definitions_schema)
    op.drop_index("ix_entity_type_schema_organization_id", table_name="entity_type_schema", schema=definitions_schema)
    op.drop_table("entity_type_schema", schema=definitions_schema)
