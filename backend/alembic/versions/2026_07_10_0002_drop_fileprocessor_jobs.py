"""Drop fileprocessor_jobs table.

The fileprocessor module is now scoped to synchronous file parsing (exposed via
the read_document tool). It no longer owns an async job engine or persistence, so
the fileprocessor_jobs table is removed.

Re-parented onto main's head (202607100001) after merge to avoid a revision-id
collision with 202607090001 (add_connector_entity_types).

Revision ID: 202607100002
Revises: 202607100001
Create Date: 2026-07-10 00:02:00
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "202607100002"
down_revision = "202607100001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    # IF EXISTS: some environments already had the table dropped under an earlier
    # (now-renumbered) revision before the merge, so guard against a re-run.
    op.execute(f'DROP TABLE IF EXISTS "{schema}".fileprocessor_jobs')


def downgrade() -> None:
    schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    op.create_table(
        "fileprocessor_jobs",
        sa.Column("job_id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("file_id", sa.String(36), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("current_stage", sa.String(64), nullable=True),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer, nullable=False, server_default="3"),
        sa.Column("priority", sa.Integer, nullable=False, server_default="5"),
        sa.Column("requested_by", sa.String(36), nullable=True),
        sa.Column("target_schema", sa.JSON, nullable=True),
        sa.Column("llm_policy", sa.JSON, nullable=False),
        sa.Column("agent_policy", sa.JSON, nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("error_code", sa.String(128), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("filename", sa.String(512), nullable=True),
        sa.Column("content_type", sa.String(255), nullable=True),
        sa.Column("storage_key", sa.String(1024), nullable=True),
        sa.Column("execution_mode", sa.String(16), nullable=True),
        sa.Column("agent_name", sa.String(128), nullable=True),
        sa.Column("agent_definition_id", sa.String(36), nullable=True),
        sa.Column("detected_format", sa.String(32), nullable=True),
        sa.Column("success", sa.Boolean, nullable=True),
        sa.Column("classification", sa.JSON, nullable=True),
        sa.Column("structured_output", sa.JSON, nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("confidence_score", sa.Float, nullable=True),
        sa.Column("warnings", sa.JSON, nullable=False),
        sa.Column("errors", sa.JSON, nullable=False),
        sa.Column("provider_trace", sa.JSON, nullable=False),
        sa.Column("stage_log", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("job_id"),
        schema=schema,
    )
    op.create_index("ix_fileprocessor_jobs_organization_id", "fileprocessor_jobs", ["organization_id"], schema=schema)
    op.create_index("ix_fileprocessor_jobs_file_id", "fileprocessor_jobs", ["file_id"], schema=schema)
    op.create_index("ix_fileprocessor_jobs_status", "fileprocessor_jobs", ["status"], schema=schema)
    op.create_index("ix_fileprocessor_jobs_org_status_created", "fileprocessor_jobs", ["organization_id", "status", "created_at"], schema=schema)
    op.create_index("ix_fileprocessor_jobs_org_file_created", "fileprocessor_jobs", ["organization_id", "file_id", "created_at"], schema=schema)
    op.create_index("ux_fileprocessor_jobs_org_idempotency", "fileprocessor_jobs", ["organization_id", "idempotency_key"], unique=True, schema=schema)
