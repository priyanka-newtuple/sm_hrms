"""Add recurring entity schedules and scheduled-entity executor.

Revision ID: 202607150001
Revises: 202607140001
Create Date: 2026-07-15 00:01:00
"""

from __future__ import annotations

import os
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "202607150001"
down_revision = "202607140001"
branch_labels = None
depends_on = None


def _schema(suffix: str) -> str:
    return f"{os.environ.get('POSTGRES_APP_SCHEMA', 'public')}_{suffix}"


def upgrade() -> None:
    definitions = _schema("definitions")
    runtime = _schema("runtime")
    op.create_table(
        "entity_schedules",
        sa.Column("schedule_id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("machine_name", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("anchor_entity_type_id", sa.String(36), nullable=False),
        sa.Column("target_entity_type_id", sa.String(36), nullable=False),
        sa.Column("relation_def_id", sa.String(36), nullable=False),
        sa.Column("recurrence_json", postgresql.JSONB(), nullable=False),
        sa.Column("lead_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("entity_data_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("identifier_template", sa.String(512), nullable=False),
        sa.Column("owner_id", sa.String(128), nullable=True),
        sa.Column("assignee_id", sa.String(128), nullable=True),
        sa.Column("conditions_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("condition_mode", sa.String(8), nullable=False, server_default="all"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("starts_on", sa.Date(), nullable=True),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("organization_id", "machine_name", "name", name="uq_entity_schedules_org_machine_name"),
        schema=definitions,
    )
    op.create_index("ix_entity_schedules_org_machine", "entity_schedules", ["organization_id", "machine_name"], schema=definitions)
    op.create_table(
        "entity_schedule_targets",
        sa.Column("target_id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("schedule_id", sa.String(36), nullable=False),
        sa.Column("anchor_entity_id", sa.String(36), nullable=False),
        sa.Column("next_due_date", sa.Date(), nullable=False),
        sa.Column("next_materialization_date", sa.Date(), nullable=False),
        sa.Column("assignee_id", sa.String(128), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_action_run_id", sa.String(36), nullable=True),
        sa.Column("last_result", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("schedule_id", "anchor_entity_id", name="uq_entity_schedule_targets_schedule_anchor"),
        schema=runtime,
    )
    op.create_index("ix_entity_schedule_targets_due", "entity_schedule_targets", ["organization_id", "is_enabled", "next_materialization_date"], schema=runtime)
    op.execute(
        sa.text(
            f'''INSERT INTO "{definitions}".action_definitions
                (definition_id, organization_id, kind, name, description, input_schema, output_schema, is_internal)
            VALUES (:id, NULL, 'entity.create_and_enroll', 'Create scheduled entity',
                'Creates a related entity and enrolls it in a workflow.',
                '{{}}'::jsonb, '{{}}'::jsonb, TRUE)
            ON CONFLICT DO NOTHING'''
        ).bindparams(id=str(uuid.uuid4()))
    )


def downgrade() -> None:
    definitions = _schema("definitions")
    runtime = _schema("runtime")
    op.execute(sa.text(f'''DELETE FROM "{definitions}".action_definitions WHERE kind = 'entity.create_and_enroll' '''))
    op.drop_index("ix_entity_schedule_targets_due", table_name="entity_schedule_targets", schema=runtime)
    op.drop_table("entity_schedule_targets", schema=runtime)
    op.drop_index("ix_entity_schedules_org_machine", table_name="entity_schedules", schema=definitions)
    op.drop_table("entity_schedules", schema=definitions)
