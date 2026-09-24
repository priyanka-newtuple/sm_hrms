"""Add content_hash column and deduplication index to files table.

Adds a SHA-256 content fingerprint column to the files table so that
duplicate uploads of the same file bytes within the same org/entity scope
can be detected and short-circuited without creating a second record.

A partial unique index on (organization_id, owner_entity_id, content_hash)
enforces deduplication at the database level. The index is partial
(content_hash IS NOT NULL) so legacy rows without a hash are unaffected.

This migration is idempotent — it checks for column and index existence
before creating them, so re-running is safe.

Revision ID: 202605290001
Revises: 202606010002
Create Date: 2026-05-29
"""

from __future__ import annotations

import logging
import os

import sqlalchemy as sa
from alembic import op

revision = "202605290001"
down_revision = "202605280001"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")


def _app_schema() -> str:
    return os.environ.get("POSTGRES_APP_SCHEMA", "public")


def upgrade() -> None:
    app_schema = _app_schema()
    conn = op.get_bind()

    # Add content_hash column if not already present
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = :s AND table_name = 'files' AND column_name = 'content_hash'"
        ).bindparams(s=app_schema)
    )
    if not result.fetchone():
        op.add_column(
            "files",
            sa.Column("content_hash", sa.String(64), nullable=True),
            schema=app_schema,
        )
        logger.info("Added content_hash column to files table")
    else:
        logger.info("content_hash column already exists, skipping")

    # Add partial unique index if not already present
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_indexes WHERE schemaname = :s AND indexname = :i"
        ).bindparams(s=app_schema, i="ux_files_org_entity_content_hash")
    )
    if not result.fetchone():
        op.create_index(
            "ux_files_org_entity_content_hash",
            "files",
            ["organization_id", "owner_entity_id", "content_hash"],
            unique=True,
            schema=app_schema,
            postgresql_where=sa.text("content_hash IS NOT NULL"),
        )
        logger.info("Created ux_files_org_entity_content_hash index on files table")
    else:
        logger.info("ux_files_org_entity_content_hash index already exists, skipping")


def downgrade() -> None:
    app_schema = _app_schema()
    op.drop_index(
        "ux_files_org_entity_content_hash",
        table_name="files",
        schema=app_schema,
        if_exists=True,
    )
    op.drop_column("files", "content_hash", schema=app_schema)
