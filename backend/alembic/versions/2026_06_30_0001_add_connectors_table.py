"""Add connectors table and seed the webhook.http action definition.

Creates the `connectors` table (reusable outbound API call definitions) and seeds the
`webhook.http` action definition so the connector action appears in the workflow designer.

Revision ID: 202606300001
Revises: 202607010001
Create Date: 2026-06-30
"""

from __future__ import annotations

import os
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "202606300001"
down_revision = "202607010001"
branch_labels = None
depends_on = None

_app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "modular_backend")


def _definitions_schema() -> str:
    return f"{os.environ.get('POSTGRES_APP_SCHEMA', 'public')}_definitions"


def upgrade() -> None:
    op.create_table(
        "connectors",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("entity_type", sa.String(128), nullable=True),
        sa.Column("base_url", sa.String(512), nullable=False),
        sa.Column("method", sa.String(8), nullable=False, server_default="POST"),
        sa.Column("path", sa.String(512), nullable=False, server_default=""),
        sa.Column("headers", JSONB(), nullable=False, server_default="{}"),
        sa.Column("query_params", JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "content_type", sa.String(64), nullable=False, server_default="application/json"
        ),
        sa.Column("body_template", JSONB(), nullable=True),
        sa.Column("auth_type", sa.String(32), nullable=False, server_default="none"),
        sa.Column("auth_config", JSONB(), nullable=False, server_default="{}"),
        sa.Column("encrypted_secret_config", sa.Text(), nullable=True),
        sa.Column("secret_hints", JSONB(), nullable=False, server_default="{}"),
        sa.Column("response_mapping", JSONB(), nullable=False, server_default="{}"),
        sa.Column("success_when", JSONB(), nullable=False, server_default="{}"),
        sa.Column("expose_as_tool", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="configured"),
        sa.Column("validation_status", sa.String(16), nullable=True),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=_app_schema,
    )
    op.create_index(
        "ix_connectors_organization_id", "connectors", ["organization_id"], schema=_app_schema
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

    # Seed the webhook.http action definition so the connector action shows in the designer.
    definitions_schema = _definitions_schema()
    op.execute(
        sa.text(f"""
            INSERT INTO "{definitions_schema}".action_definitions
                (definition_id, organization_id, kind, name, description, input_schema, output_schema, is_internal)
            VALUES (
                '{uuid.uuid4()}',
                NULL,
                'webhook.http',
                'Call External API',
                'Call an external system via an approved connector when an entity enters a state.',
                '{{"connector_id": {{"type": "string"}}}}'::jsonb,
                '{{"outcome": {{"type": "string", "enum": ["success", "failed"]}}}}'::jsonb,
                FALSE
            )
            ON CONFLICT DO NOTHING;
        """)
    )


def downgrade() -> None:
    definitions_schema = _definitions_schema()
    op.execute(
        sa.text(
            f'DELETE FROM "{definitions_schema}".action_definitions WHERE kind = \'webhook.http\';'
        )
    )
    op.drop_index("ix_connectors_org_entity_type", table_name="connectors", schema=_app_schema)
    op.drop_index("ix_connectors_entity_type", table_name="connectors", schema=_app_schema)
    op.drop_index("ix_connectors_organization_id", table_name="connectors", schema=_app_schema)
    op.drop_table("connectors", schema=_app_schema)
