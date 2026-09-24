"""Backfill field_library:* role permissions from the form:* grants.

The field library used to ride on form:read / form:write. It now has its own
scope, so it can be granted independently of Forms access. Without this backfill
every existing role would lose field library access the moment the code switched
over, which is why it ships alongside that switch rather than after it.

Each existing role_permissions row for form:read gains a matching
field_library:read row with the same role_id and the same `allowed` value, so a
role that was explicitly denied stays denied. Same for write. Everything else on
the copied row is left null.

Only pre-existing roles need this. Organizations created from here on get the
new keys for free, since new roles are seeded from the full permission catalog.

There is no unique constraint on (role_id, permission_key), so idempotency is
the migration's own job: each insert is guarded by NOT EXISTS rather than
relying on a conflict.

The revision id skips ahead to ...0003 on purpose. The stacked Method Library
branch already claims 202608220001 and 202608220002, and both branches land in
the same tree, where a duplicate id would stop Alembic dead.

Revision ID: 202608220003
Revises: 202608210002
Create Date: 2026-08-22
"""

from __future__ import annotations

import os
import uuid

import sqlalchemy as sa

from alembic import op

revision = "202608220003"
down_revision = "202608210002"
branch_labels = None
depends_on = None

_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")

# The grant each new key inherits from.
PERMISSION_BACKFILL = (
    ("form:read", "field_library:read"),
    ("form:write", "field_library:write"),
)

_SELECT_SOURCE_GRANTS = """
    SELECT role_id, allowed
    FROM "{schema}".role_permissions
    WHERE permission_key = :source_key
"""

_INSERT_GRANT = """
    INSERT INTO "{schema}".role_permissions (id, role_id, permission_key, allowed)
    SELECT :id, :role_id, :target_key, :allowed
    WHERE NOT EXISTS (
        SELECT 1 FROM "{schema}".role_permissions
        WHERE role_id = :role_id AND permission_key = :target_key
    )
"""

_DELETE_GRANTS = """
    DELETE FROM "{schema}".role_permissions
    WHERE permission_key IN ('field_library:read', 'field_library:write')
"""


def backfill_field_library_permissions(conn) -> int:
    """Copy every form:* grant into its field_library:* counterpart.

    Returns how many rows were inserted. Safe to run again: a role that already
    has the target key is skipped, so a second run inserts nothing.
    """
    inserted = 0
    for source_key, target_key in PERMISSION_BACKFILL:
        rows = conn.execute(
            sa.text(_SELECT_SOURCE_GRANTS.format(schema=_schema)),
            {"source_key": source_key},
        ).fetchall()
        for role_id, allowed in rows:
            result = conn.execute(
                sa.text(_INSERT_GRANT.format(schema=_schema)),
                {
                    "id": str(uuid.uuid4()),
                    "role_id": role_id,
                    "target_key": target_key,
                    "allowed": allowed,
                },
            )
            inserted += result.rowcount or 0
    return inserted


def upgrade() -> None:
    backfill_field_library_permissions(op.get_bind())


def downgrade() -> None:
    # Only the keys this migration introduced. The form:* rows it read from are
    # left exactly as they were.
    op.get_bind().execute(sa.text(_DELETE_GRANTS.format(schema=_schema)))
