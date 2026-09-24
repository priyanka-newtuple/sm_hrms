"""Add composite indexes for recency-ordered entity and enrollment summaries.

Mirrors the `created_at` indexes from 202607190001 on the columns those
queries now sort by. The old ones stay for the explicit `sort_by=created`.

Revision ID: 202608270001
Revises: 202608250002
Create Date: 2026-08-27 00:01:00
"""

from __future__ import annotations

import os

from alembic import op

revision = "202608270001"
down_revision = "202608250002"
branch_labels = None
depends_on = None


def _runtime_schema() -> str:
    return f"{os.environ.get('POSTGRES_APP_SCHEMA', 'public')}_runtime"


def upgrade() -> None:
    schema = _runtime_schema()
    op.create_index(
        "ix_runtime_entities_org_type_active_updated",
        "entities",
        ["organization_id", "entity_type_id", "archived_at", "updated_at", "entity_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_runtime_entity_state_org_state_entered",
        "entity_state",
        ["organization_id", "current_state", "state_entered_at", "state_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_runtime_entity_state_org_workflow_entered",
        "entity_state",
        ["organization_id", "workflow_id", "state_entered_at", "state_id"],
        unique=False,
        schema=schema,
    )


def downgrade() -> None:
    schema = _runtime_schema()
    op.drop_index(
        "ix_runtime_entity_state_org_workflow_entered", table_name="entity_state", schema=schema
    )
    op.drop_index(
        "ix_runtime_entity_state_org_state_entered", table_name="entity_state", schema=schema
    )
    op.drop_index(
        "ix_runtime_entities_org_type_active_updated", table_name="entities", schema=schema
    )
