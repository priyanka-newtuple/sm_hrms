"""Add agent_runs table for phase-1 agent runtime.

Revision ID: 202606200001
Revises: 202606180002
Create Date: 2026-06-20
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "202606200001"
down_revision = "202606180002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    op.create_table(
        "agent_runs",
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("definition_id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=True),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("output_text", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("backend_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("execution_context", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["definition_id"],
            [f"{schema}.agent_definitions.definition_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            [f"{schema}.agent_sessions.session_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("run_id", name="pk_agent_runs"),
        schema=schema,
    )
    op.create_index("ix_agent_runs_organization_id", "agent_runs", ["organization_id"], schema=schema)
    op.create_index("ix_agent_runs_definition_id", "agent_runs", ["definition_id"], schema=schema)
    op.create_index("ix_agent_runs_session_id", "agent_runs", ["session_id"], schema=schema)
    op.create_index("ix_agent_runs_user_id", "agent_runs", ["user_id"], schema=schema)
    op.create_index("ix_agent_runs_org_created", "agent_runs", ["organization_id", "created_at"], schema=schema)
    op.create_index("ix_agent_runs_org_status", "agent_runs", ["organization_id", "status"], schema=schema)


def downgrade() -> None:
    schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    op.drop_index("ix_agent_runs_org_status", table_name="agent_runs", schema=schema)
    op.drop_index("ix_agent_runs_org_created", table_name="agent_runs", schema=schema)
    op.drop_index("ix_agent_runs_user_id", table_name="agent_runs", schema=schema)
    op.drop_index("ix_agent_runs_session_id", table_name="agent_runs", schema=schema)
    op.drop_index("ix_agent_runs_definition_id", table_name="agent_runs", schema=schema)
    op.drop_index("ix_agent_runs_organization_id", table_name="agent_runs", schema=schema)
    op.drop_table("agent_runs", schema=schema)
