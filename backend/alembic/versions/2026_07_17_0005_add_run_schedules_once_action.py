"""Add the workflow action for running one automation batch.

Revision ID: 202607170005
Revises: 202607170004
Create Date: 2026-07-17 00:05:00
"""

from __future__ import annotations

import os

import sqlalchemy as sa

from alembic import op

revision = "202607170005"
down_revision = "202607170004"
branch_labels = None
depends_on = None


def _definitions_schema() -> str:
    return f"{os.environ.get('POSTGRES_APP_SCHEMA', 'public')}_definitions"


def upgrade() -> None:
    schema = _definitions_schema()
    op.execute(
        sa.text(
            f'''INSERT INTO "{schema}".action_definitions
                (definition_id, organization_id, kind, name, description,
                 input_schema, output_schema, is_internal)
            VALUES (
                '48e2f89f-73ce-4f73-b28a-68121dfb5ec0', NULL,
                'entity.run_schedules_once', 'Run automations once',
                'Create one configured occurrence batch for the entity entering this state.',
                '{{"schedule_ids": {{"type": "array", "items": {{"type": "string"}}}},
                  "activation_policy": {{"type": "string", "enum": ["current_period", "next_occurrence"]}}}}'::jsonb,
                '{{"outcome": {{"type": "string", "enum": ["queued", "failed"]}}}}'::jsonb,
                FALSE
            ) ON CONFLICT DO NOTHING'''
        )
    )


def downgrade() -> None:
    schema = _definitions_schema()
    op.execute(
        sa.text(
            f'''DELETE FROM "{schema}".action_definitions
                WHERE definition_id = '48e2f89f-73ce-4f73-b28a-68121dfb5ec0' '''
        )
    )
