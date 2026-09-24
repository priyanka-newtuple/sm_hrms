"""Allow duplicate file content while retaining content-hash lookup support.

Revision ID: 202607160003
Revises: 202607160002
Create Date: 2026-07-16
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "202607160003"
down_revision = "202607150003"
branch_labels = None
depends_on = None


def _app_schema() -> str:
    return os.environ.get("POSTGRES_APP_SCHEMA", "public")


def upgrade() -> None:
    schema = _app_schema()
    op.drop_index(
        "ux_files_org_entity_content_hash",
        table_name="files",
        schema=schema,
        if_exists=True,
    )
    op.create_index(
        "ix_files_org_entity_content_hash",
        "files",
        ["organization_id", "owner_entity_id", "content_hash"],
        unique=False,
        schema=schema,
        postgresql_where=sa.text("content_hash IS NOT NULL"),
        if_not_exists=True,
    )


def downgrade() -> None:
    schema = _app_schema()
    op.drop_index(
        "ix_files_org_entity_content_hash",
        table_name="files",
        schema=schema,
        if_exists=True,
    )
    op.create_index(
        "ux_files_org_entity_content_hash",
        "files",
        ["organization_id", "owner_entity_id", "content_hash"],
        unique=True,
        schema=schema,
        postgresql_where=sa.text("content_hash IS NOT NULL"),
        if_not_exists=True,
    )
