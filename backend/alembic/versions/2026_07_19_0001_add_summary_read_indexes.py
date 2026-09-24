"""Add composite indexes for paginated entity and enrollment summaries.

Revision ID: 202607190001
Revises: 202607170007
Create Date: 2026-07-19 00:01:00
"""

from __future__ import annotations

import os

from alembic import op

revision = "202607190001"
down_revision = "202607170007"
branch_labels = None
depends_on = None


def _runtime_schema() -> str:
    return f"{os.environ.get('POSTGRES_APP_SCHEMA', 'public')}_runtime"


def _app_schema() -> str:
    return os.environ.get("POSTGRES_APP_SCHEMA", "public")


def upgrade() -> None:
    schema = _runtime_schema()
    op.create_index(
        "ix_runtime_entities_org_type_active_created",
        "entities",
        ["organization_id", "entity_type_id", "archived_at", "created_at", "entity_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_files_org_type_entity_created",
        "files",
        ["organization_id", "type_id", "owner_entity_id", "created_at"],
        unique=False,
        schema=_app_schema(),
    )
    op.create_index(
        "ix_runtime_entity_state_org_state_created",
        "entity_state",
        ["organization_id", "current_state", "created_at", "state_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_runtime_entity_state_org_workflow_created",
        "entity_state",
        ["organization_id", "workflow_id", "created_at", "state_id"],
        unique=False,
        schema=schema,
    )


def downgrade() -> None:
    schema = _runtime_schema()
    op.drop_index(
        "ix_files_org_type_entity_created", table_name="files", schema=_app_schema()
    )
    op.drop_index(
        "ix_runtime_entity_state_org_workflow_created", table_name="entity_state", schema=schema
    )
    op.drop_index(
        "ix_runtime_entity_state_org_state_created", table_name="entity_state", schema=schema
    )
    op.drop_index(
        "ix_runtime_entities_org_type_active_created", table_name="entities", schema=schema
    )
