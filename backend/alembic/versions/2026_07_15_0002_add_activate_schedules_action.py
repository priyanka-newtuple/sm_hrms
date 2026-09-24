"""Add the workflow action for activating recurring schedules.

Revision ID: 202607150002
Revises: 202607150001
Create Date: 2026-07-15 00:02:00
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "202607150002"
down_revision = "202607150001"
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
                '2ead9845-e928-44aa-9980-6ea1ddbc95a8', NULL,
                'entity.activate_schedules', 'Activate recurring schedules',
                'Subscribe an entity to selected schedules when it enters this state.',
                '{{"schedule_ids": {{"type": "array", "items": {{"type": "string"}}}},
                  "activation_policy": {{"type": "string", "enum": ["current_period", "next_occurrence"]}}}}'::jsonb,
                '{{"outcome": {{"type": "string", "enum": ["activated", "failed"]}}}}'::jsonb,
                FALSE
            ) ON CONFLICT DO NOTHING'''
        )
    )


def downgrade() -> None:
    schema = _definitions_schema()
    op.execute(
        sa.text(
            f'''DELETE FROM "{schema}".action_definitions
                WHERE definition_id = '2ead9845-e928-44aa-9980-6ea1ddbc95a8' '''
        )
    )
