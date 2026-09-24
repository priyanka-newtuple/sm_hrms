"""Add storage_provider column to files table.

Tracks where a file's bytes live — 'local' for the on-disk filesystem
or 'azure' for Azure Blob Storage. Existing rows default to 'local'.

This migration is idempotent — it checks for column existence before
adding it, so re-running is safe.

Revision ID: 202606150001
Revises: 202606120001
Create Date: 2026-06-15
"""

from __future__ import annotations

import logging
import os

import sqlalchemy as sa
from alembic import op

revision = "202606150001"
down_revision = "202606120001"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")


def _app_schema() -> str:
    return os.environ.get("POSTGRES_APP_SCHEMA", "public")


def upgrade() -> None:
    app_schema = _app_schema()
    conn = op.get_bind()

    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = :s AND table_name = 'files' AND column_name = 'storage_provider'"
        ).bindparams(s=app_schema)
    )
    if not result.fetchone():
        op.add_column(
            "files",
            sa.Column("storage_provider", sa.String(32), nullable=True, server_default="local"),
            schema=app_schema,
        )
        logger.info("Added storage_provider column to files table")
    else:
        logger.info("storage_provider column already exists, skipping")


def downgrade() -> None:
    app_schema = _app_schema()
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = :s AND table_name = 'files' AND column_name = 'storage_provider'"
        ).bindparams(s=app_schema)
    )
    if result.fetchone():
        op.drop_column("files", "storage_provider", schema=app_schema)
