"""Ensure field_library_field_versions.field_type exists, backfilled and NOT NULL.

Repair migration. 202608180002 was amended in place to create this column while
the branch was unreleased, so a database migrated before that amendment is
recorded as already past 202608180002 and will never receive it. Anything reading
a field version then fails on a missing column.

Idempotent on purpose: a database created from the amended 202608180002 already
has the column, so this is a no-op there, while a database stamped before the
amendment gets the column added, backfilled and tightened.

The backfill takes each version's type from its field's current type in
field_library_fields. Those rows predate type versioning, so the two necessarily
agreed when they were written, and the foreign key guarantees every version has a
parent to read from.

Revision ID: 202608210002
Revises: 202608210001
Create Date: 2026-08-21
"""

from __future__ import annotations

import os

import sqlalchemy as sa

from alembic import op

revision = "202608210002"
down_revision = "202608210001"
branch_labels = None
depends_on = None

VERSIONS_TABLE = "field_library_field_versions"
FIELDS_TABLE = "field_library_fields"
COLUMN_NAME = "field_type"
FIELD_TYPE_CODE_LENGTH = 64


def _definitions_schema() -> str:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return f"{app_schema}_definitions"


def _column_exists(schema: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns(VERSIONS_TABLE, schema=schema)}
    return COLUMN_NAME in columns


def upgrade() -> None:
    definitions_schema = _definitions_schema()
    if _column_exists(definitions_schema):
        # Created by the amended 202608180002; nothing to repair.
        return

    # Nullable first, so existing rows are accepted before they are populated.
    op.add_column(
        VERSIONS_TABLE,
        sa.Column(COLUMN_NAME, sa.String(FIELD_TYPE_CODE_LENGTH), nullable=True),
        schema=definitions_schema,
    )
    op.execute(
        sa.text(
            f"""
            UPDATE "{definitions_schema}".{VERSIONS_TABLE} AS v
            SET {COLUMN_NAME} = f.{COLUMN_NAME}
            FROM "{definitions_schema}".{FIELDS_TABLE} AS f
            WHERE v.library_field_id = f.library_field_id
            """
        )
    )
    op.alter_column(
        VERSIONS_TABLE,
        COLUMN_NAME,
        existing_type=sa.String(FIELD_TYPE_CODE_LENGTH),
        nullable=False,
        schema=definitions_schema,
    )


def downgrade() -> None:
    """Deliberately a no-op: this revision must never drop the column.

    Whether the column exists says nothing about whether this revision is the
    one that added it. On a database created from the amended 202608180002 the
    upgrade above did nothing, so dropping the column here would remove one that
    202608180002 owns and still declares, leaving the schema inconsistent with an
    applied migration and breaking every read of field_type.

    Leaving it in place is safe in the other direction too. On a pre-amendment
    database the column simply stays, already backfilled and NOT NULL, and a
    later re-upgrade sees it and no-ops. Going further back is unaffected either
    way: 202608180002's own downgrade drops the whole versions table.
    """
