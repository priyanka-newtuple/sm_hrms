"""Seed agent_run action definition for the generic agent executor.

Revision ID: 202607100001
Revises: 202607090001
Create Date: 2026-07-10
"""

from __future__ import annotations

import os
import uuid

import sqlalchemy as sa
from alembic import op

revision = "202607100001"
down_revision = "202607090001"
branch_labels = None
depends_on = None


def _definitions_schema() -> str:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return f"{app_schema}_definitions"


def upgrade() -> None:
    definitions_schema = _definitions_schema()
    op.execute(
        sa.text(f"""
            INSERT INTO "{definitions_schema}".action_definitions
                (definition_id, organization_id, kind, name, description, input_schema, output_schema, is_internal)
            VALUES (
                '{uuid.uuid4()}',
                NULL,
                'agent_run',
                'Run AI Agent',
                'Runs a configured AI agent on state entry, maps its JSON output back onto entity fields, and routes the outcome to a transition.',
                '{{"agent_id": {{"type": "string"}}, "input_fields": {{"type": "array"}}, "include_files": {{"type": "boolean"}}, "include_relations": {{"type": "array"}}, "output_mapping": {{"type": "object"}}, "prompt_instructions": {{"type": "string"}}}}'::jsonb,
                '{{"outcome": {{"type": "string", "enum": ["success", "failed"]}}}}'::jsonb,
                FALSE
            )
            ON CONFLICT DO NOTHING;
        """)
    )


def downgrade() -> None:
    definitions_schema = _definitions_schema()
    op.execute(
        sa.text(f"""
            DELETE FROM "{definitions_schema}".action_definitions WHERE kind = 'agent_run';
        """)
    )
