"""Seed signal.fire action definition for generic signal executor.

Revision ID: 202606190001
Revises: 202606200001
Create Date: 2026-06-19
"""

from __future__ import annotations

import os
import uuid

import sqlalchemy as sa
from alembic import op

revision = "202606190001"
down_revision = "202606200001"
branch_labels = None
depends_on = None


def _definitions_schema() -> str:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return f"{app_schema}_definitions"


def upgrade() -> None:
    definitions_schema = _definitions_schema()
    op.execute(
        sa.text(f"""
            ALTER TABLE "{definitions_schema}".action_definitions
            ADD COLUMN IF NOT EXISTS is_internal BOOLEAN NOT NULL DEFAULT FALSE;
        """)
    )
    op.execute(
        sa.text(f"""
            UPDATE "{definitions_schema}".action_definitions
            SET is_internal = FALSE
            WHERE kind IN ('form.receive_data', 'mail.send_email');
        """)
    )
    op.execute(
        sa.text(f"""
            INSERT INTO "{definitions_schema}".action_definitions
                (definition_id, organization_id, kind, name, description, input_schema, output_schema, is_internal)
            VALUES (
                '{uuid.uuid4()}',
                NULL,
                'signal.fire',
                'Signal Executor',
                'Executes a sequence of steps (notify, email, trigger) from config_json. Used for SLA breach, reminders, and escalations.',
                '{{"signal_type": {{"type": "string"}}, "steps": {{"type": "array"}}}}'::jsonb,
                '{{"outcome": {{"type": "string", "enum": ["completed", "no_recipient_found", "failed"]}}}}'::jsonb,
                TRUE
            )
            ON CONFLICT DO NOTHING;
        """)
    )


def downgrade() -> None:
    definitions_schema = _definitions_schema()
    op.execute(
        sa.text(f"""
            DELETE FROM "{definitions_schema}".action_definitions WHERE kind = 'signal.fire';
        """)
    )
    op.drop_column("action_definitions", "is_internal", schema=definitions_schema)
