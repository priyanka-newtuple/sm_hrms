"""Add intake_jobs table for persistent background intake job tracking.

Replaces the in-memory dict that was lost on server restart.

Revision ID: 202606180003
Revises: 202606190001
Create Date: 2026-06-18
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "202606180003"
down_revision = "202606190001"
branch_labels = None
depends_on = None

_app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "modular_backend")


def upgrade() -> None:
    op.create_table(
        "intake_jobs",
        sa.Column("job_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("source_type", sa.String(100), nullable=False),
        sa.Column("file_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("subject_entity_type", sa.String(255), nullable=True),
        sa.Column("files_json", JSONB(), nullable=False, server_default="[]"),
        sa.Column("context_json", JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("job_id"),
        schema=_app_schema,
    )
    op.create_index(
        "ix_intake_jobs_org",
        "intake_jobs",
        ["organization_id"],
        schema=_app_schema,
    )
    op.create_index(
        "ix_intake_jobs_org_status",
        "intake_jobs",
        ["organization_id", "status"],
        schema=_app_schema,
    )


def downgrade() -> None:
    op.drop_index("ix_intake_jobs_org_status", table_name="intake_jobs", schema=_app_schema)
    op.drop_index("ix_intake_jobs_org", table_name="intake_jobs", schema=_app_schema)
    op.drop_table("intake_jobs", schema=_app_schema)
