"""Ensure method_library_method_version_fields.inherit_from exists.

Forward-only repair for the 202608280001 chain splice, which left
production without this column even after `upgrade head` (see
design_docs/PROD_MIGRATION_RUNBOOK.md for the investigation). Adds the
column only if missing, tagged so downgrade removes only what this
migration itself created.

Revision ID: 202609050001
Revises: 202609010002
Create Date: 2026-09-05
"""

from __future__ import annotations

import os

import sqlalchemy as sa

from alembic import op

revision = "202609050001"
down_revision = "202609010002"
branch_labels = None
depends_on = None

TABLE_NAME = "method_library_method_version_fields"
COLUMN_NAME = "inherit_from"
# Mirrors method_library.models.interface.INHERIT_FROM_MAX_LENGTH and the
# length used by 202608280001. Not imported: migrations here never import
# app code.
COLUMN_LENGTH = 300
CREATED_HERE_MARKER = "created by alembic revision 202609050001 (chain repair for 202608280001)"


def _definitions_schema() -> str:
    return f"{os.environ.get('POSTGRES_APP_SCHEMA', 'public')}_definitions"


def _column_exists(conn, schema: str) -> bool:
    return (
        conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = :schema AND table_name = :table "
                "AND column_name = :column"
            ),
            {"schema": schema, "table": TABLE_NAME, "column": COLUMN_NAME},
        ).first()
        is not None
    )


def _column_comment(conn, schema: str) -> str | None:
    return conn.execute(
        sa.text(
            "SELECT col_description(c.oid, a.attnum) "
            "FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "JOIN pg_attribute a ON a.attrelid = c.oid "
            "WHERE n.nspname = :schema AND c.relname = :table "
            "AND a.attname = :column AND NOT a.attisdropped"
        ),
        {"schema": schema, "table": TABLE_NAME, "column": COLUMN_NAME},
    ).scalar()


def upgrade() -> None:
    conn = op.get_bind()
    schema = _definitions_schema()

    if _column_exists(conn, schema):
        # 202608280001 ran in order here (or this migration already ran).
        return

    conn.execute(
        sa.text(
            f'ALTER TABLE "{schema}"."{TABLE_NAME}" '
            f'ADD COLUMN "{COLUMN_NAME}" VARCHAR({COLUMN_LENGTH}) NULL'
        )
    )
    conn.execute(
        sa.text(
            f'COMMENT ON COLUMN "{schema}"."{TABLE_NAME}"."{COLUMN_NAME}" '
            f"IS :marker"
        ),
        {"marker": CREATED_HERE_MARKER},
    )


def downgrade() -> None:
    conn = op.get_bind()
    schema = _definitions_schema()

    if not _column_exists(conn, schema):
        return
    if _column_comment(conn, schema) != CREATED_HERE_MARKER:
        # Column was created by 202608280001, not by us - leave it to that
        # revision's downgrade.
        return

    conn.execute(
        sa.text(f'ALTER TABLE "{schema}"."{TABLE_NAME}" DROP COLUMN "{COLUMN_NAME}"')
    )
