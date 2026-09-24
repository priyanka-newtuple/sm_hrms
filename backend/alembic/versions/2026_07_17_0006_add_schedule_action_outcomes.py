"""Add explicit no-op outcomes for one-time automation actions.

Revision ID: 202607170006
Revises: 202607170005
Create Date: 2026-07-17 00:06:00
"""

from __future__ import annotations

import os

import sqlalchemy as sa

from alembic import op

revision = "202607170006"
down_revision = "202607170005"
branch_labels = None
depends_on = None


def _definitions_schema() -> str:
    return f"{os.environ.get('POSTGRES_APP_SCHEMA', 'public')}_definitions"


def upgrade() -> None:
    schema = _definitions_schema()
    op.execute(
        sa.text(
            f'''UPDATE "{schema}".action_definitions
                SET output_schema = '{{"outcome": {{"type": "string", "enum":
                    ["queued", "already_invoked", "skipped", "failed"]}}}}'::jsonb
                WHERE kind = 'entity.run_schedules_once' '''
        )
    )


def downgrade() -> None:
    schema = _definitions_schema()
    op.execute(
        sa.text(
            f'''UPDATE "{schema}".action_definitions
                SET output_schema = '{{"outcome": {{"type": "string", "enum":
                    ["queued", "failed"]}}}}'::jsonb
                WHERE kind = 'entity.run_schedules_once' '''
        )
    )
