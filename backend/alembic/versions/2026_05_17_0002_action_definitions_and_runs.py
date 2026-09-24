"""Add action_definitions, action_runs tables and seed initial action definitions.

Revision ID: 202605170002
Revises: 202605170001
Create Date: 2026-05-17
"""

from __future__ import annotations

import os
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "202605170002"
down_revision = "202605170001"
branch_labels = None
depends_on = None


def _app_schema() -> str:
    return os.environ.get("POSTGRES_APP_SCHEMA", "public")


def _definitions_schema() -> str:
    return _app_schema() + "_definitions"


def upgrade() -> None:
    app_schema = _app_schema()
    definitions_schema = _definitions_schema()

    # -- action_definitions catalog --
    op.create_table(
        "action_definitions",
        sa.Column("definition_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=True),
        sa.Column("kind", sa.String(128), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("input_schema", JSONB, nullable=False, server_default="{}"),
        sa.Column("output_schema", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("definition_id", name="pk_action_definitions"),
        schema=definitions_schema,
    )
    op.create_index(
        "ix_action_definitions_kind", "action_definitions", ["kind"], schema=definitions_schema
    )
    op.create_index(
        "ix_action_definitions_org",
        "action_definitions",
        ["organization_id"],
        schema=definitions_schema,
    )

    # -- seed action definitions --
    op.execute(
        sa.text(f"""
            INSERT INTO "{definitions_schema}".action_definitions
                (definition_id, organization_id, kind, name, description, input_schema, output_schema)
            VALUES
                (
                    '{uuid.uuid4()}',
                    NULL,
                    'form.receive_data',
                    'Receive Form Data',
                    'Pause the workflow and wait for the entity form to be submitted by an external user.',
                    '{{"form_id": {{"type": "string"}}, "timeout_hours": {{"type": "integer"}}}}'::jsonb,
                    '{{"outcome": {{"type": "string", "enum": ["waiting", "received", "failed"]}}}}'::jsonb
                ),
                (
                    '{uuid.uuid4()}',
                    NULL,
                    'mail.send_email',
                    'Send Email',
                    'Send an email using a template. The trigger fires immediately once the email is sent.',
                    '{{"org_id": {{"type": "string"}}, "entity_id": {{"type": "string"}}, "to": {{"type": "string"}}, "template_id": {{"type": "string"}}}}'::jsonb,
                    '{{"outcome": {{"type": "string", "enum": ["sent", "failed"]}}}}'::jsonb
                )
            ON CONFLICT DO NOTHING;
        """)
    )

    # -- action_runs execution tracking --
    op.create_table(
        "action_runs",
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("definition_id", sa.String(36), nullable=True),
        sa.Column("action_kind", sa.String(128), nullable=False),
        sa.Column("config_json", JSONB, nullable=False, server_default="{}"),
        sa.Column("resolved_config_json", JSONB, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("outcome", sa.String(64), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.String(256), nullable=True),
        sa.Column("external_timeout_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("run_id", name="pk_action_runs"),
        sa.UniqueConstraint("idempotency_key", name="uq_action_runs_idempotency_key"),
        schema=app_schema,
    )
    op.create_index("ix_action_runs_entity_id", "action_runs", ["entity_id"], schema=app_schema)
    op.create_index("ix_action_runs_status", "action_runs", ["status"], schema=app_schema)
    op.create_index("ix_action_runs_org", "action_runs", ["organization_id"], schema=app_schema)
    op.create_index(
        "ix_action_runs_sweep",
        "action_runs",
        ["status", "external_timeout_at"],
        schema=app_schema,
    )


def downgrade() -> None:
    app_schema = _app_schema()
    definitions_schema = _definitions_schema()

    op.drop_index("ix_action_runs_sweep", table_name="action_runs", schema=app_schema)
    op.drop_index("ix_action_runs_org", table_name="action_runs", schema=app_schema)
    op.drop_index("ix_action_runs_status", table_name="action_runs", schema=app_schema)
    op.drop_index("ix_action_runs_entity_id", table_name="action_runs", schema=app_schema)
    op.drop_table("action_runs", schema=app_schema)

    op.drop_index(
        "ix_action_definitions_org", table_name="action_definitions", schema=definitions_schema
    )
    op.drop_index(
        "ix_action_definitions_kind", table_name="action_definitions", schema=definitions_schema
    )
    op.drop_table("action_definitions", schema=definitions_schema)
