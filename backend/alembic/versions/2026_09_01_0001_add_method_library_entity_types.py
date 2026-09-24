"""Tag Method Library methods to the entity types they apply to.

A method is offered on a workflow state only when it is tagged with that
workflow's entity type, so the upgrade backfills a tag for every method a
workflow already references. Without it, previously-working states would
silently lose their method from the picker on deploy.

``entity_type`` is stored as text with no foreign key, matching
``workflow_state_machines.entity_type``: live workflows reference entity
types that were never registered in ``entity_types``, and a key here would
fail the backfill on exactly those rows.

Revision ID: 202609010001
Revises: 202608300001
Create Date: 2026-09-01
"""

from __future__ import annotations

import os

import sqlalchemy as sa

from alembic import op

revision = "202609010001"
down_revision = "202608300001"
branch_labels = None
depends_on = None

TABLE_NAME = "method_library_method_entity_types"


def _app_schema() -> str:
    return os.environ.get("POSTGRES_APP_SCHEMA", "public")


def _definitions_schema() -> str:
    return f"{_app_schema()}_definitions"


def upgrade() -> None:
    schema = _definitions_schema()
    app_schema = _app_schema()

    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("method_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("entity_type", sa.String(128), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "organization_id",
            "method_id",
            "entity_type",
            name="uq_method_entity_types_org_method_entity",
        ),
        sa.ForeignKeyConstraint(
            ["method_id", "organization_id"],
            [
                f"{schema}.method_library_methods.method_id",
                f"{schema}.method_library_methods.organization_id",
            ],
            name="fk_method_entity_types_method",
            ondelete="CASCADE",
        ),
        schema=schema,
    )
    op.create_index(
        "ix_method_entity_types_org_entity",
        TABLE_NAME,
        ["organization_id", "entity_type"],
        schema=schema,
    )
    op.create_index(
        "ix_method_entity_types_method_id", TABLE_NAME, ["method_id"], schema=schema
    )

    # Backfill. ``definition_json`` covers drafts as well as published rows, so
    # it is a strict superset of workflow_method_pins; archived workflows and the
    # 'entity' sentinel are skipped. Orphaned method_ids are dropped by the join
    # rather than failing the migration on the new foreign key.
    op.execute(
        sa.text(
            f"""
            INSERT INTO "{schema}".{TABLE_NAME}
                (id, method_id, organization_id, entity_type, created_at)
            SELECT DISTINCT
                gen_random_uuid()::text,
                ref->>'method_id',
                w.organization_id,
                w.entity_type,
                now()
            FROM "{app_schema}".workflow_state_machines w
            CROSS JOIN LATERAL jsonb_array_elements(
                COALESCE(w.definition_json::jsonb->'states', '[]'::jsonb)
            ) st
            CROSS JOIN LATERAL jsonb_array_elements(
                COALESCE(st->'method_refs', '[]'::jsonb)
            ) ref
            JOIN "{schema}".method_library_methods m
              ON m.method_id = ref->>'method_id'
             AND m.organization_id = w.organization_id
            WHERE w.archived_at IS NULL
              AND w.entity_type IS NOT NULL
              AND w.entity_type <> 'entity'
              AND ref->>'method_id' IS NOT NULL
            ON CONFLICT ON CONSTRAINT uq_method_entity_types_org_method_entity DO NOTHING
            """
        )
    )


def downgrade() -> None:
    schema = _definitions_schema()
    op.drop_index("ix_method_entity_types_method_id", TABLE_NAME, schema=schema)
    op.drop_index("ix_method_entity_types_org_entity", TABLE_NAME, schema=schema)
    op.drop_table(TABLE_NAME, schema=schema)
