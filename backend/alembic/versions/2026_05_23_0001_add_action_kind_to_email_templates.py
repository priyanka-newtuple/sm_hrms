"""Add action_kind column to email_templates table.

Revision ID: 202605230001
Revises: 202605170002
Create Date: 2026-05-23
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "202605230001"
down_revision = "202605170002"
branch_labels = None
depends_on = None

_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public") + "_definitions"


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(sa.text(
        f"SELECT 1 FROM information_schema.columns "
        f"WHERE table_schema = '{_schema}' AND table_name = 'email_templates' AND column_name = 'action_kind'"
    ))
    if not result.fetchone():
        op.add_column(
            "email_templates",
            sa.Column("action_kind", sa.String(64), nullable=True),
            schema=_schema,
        )


def downgrade() -> None:
    op.drop_column("email_templates", "action_kind", schema=_schema)
