"""Add all-versus-selected schedule target scope.

Revision ID: 202607170003
Revises: 202607170002
Create Date: 2026-07-17 00:03:00
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "202607170003"
down_revision = "202607170002"
branch_labels = None
depends_on = None


def _schema(suffix: str) -> str:
    return f"{os.environ.get('POSTGRES_APP_SCHEMA', 'public')}_{suffix}"


def upgrade() -> None:
    definitions = _schema("definitions")
    runtime = _schema("runtime")
    op.add_column(
        "entity_schedules",
        sa.Column("target_scope", sa.String(16), nullable=False, server_default="selected"),
        schema=definitions,
    )
    op.execute(
        sa.text(
            f'''UPDATE "{definitions}".entity_schedules AS schedule
                SET target_scope = 'all'
                WHERE NOT EXISTS (
                    SELECT 1 FROM "{runtime}".entity_schedule_targets AS target
                    WHERE target.schedule_id = schedule.schedule_id
                )'''
        )
    )
    op.alter_column(
        "entity_schedules",
        "target_scope",
        server_default="all",
        schema=definitions,
    )


def downgrade() -> None:
    op.drop_column("entity_schedules", "target_scope", schema=_schema("definitions"))
