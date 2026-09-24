"""Backfill UserOrganization rows for all superadmins across every org.

Superadmin users are platform-level — they must be members of every org so
`/users/me/organizations` returns the full org list and `switch_organization`
works without special-casing the role.

This migration is idempotent — a NOT EXISTS guard skips memberships that
already exist. Safe to re-run if new superadmins or orgs are added later.

Revision ID: 202605130001
Revises: 202605060002
Create Date: 2026-05-13
"""

from __future__ import annotations

import os
import uuid

from alembic import op


revision = "202605130001"
down_revision = "202605060002"
branch_labels = None
depends_on = None


def _schema() -> str:
    return os.environ.get("POSTGRES_APP_SCHEMA", "public")


def upgrade() -> None:
    schema = _schema()
    conn = op.get_bind()

    pairs = conn.exec_driver_sql(
        f"""
        SELECT u.id AS user_id, o.id AS org_id
        FROM "{schema}".users u
        CROSS JOIN "{schema}".organizations o
        WHERE u.role = 'superadmin'
          AND NOT EXISTS (
              SELECT 1
              FROM "{schema}".user_organizations uo
              WHERE uo.user_id = u.id
                AND uo.organization_id = o.id
          )
        """
    ).fetchall()

    if not pairs:
        return

    for row in pairs:
        conn.exec_driver_sql(
            f"""
            INSERT INTO "{schema}".user_organizations
                (id, user_id, organization_id, role, status, created_at, updated_at)
            VALUES (%s, %s, %s, 'superadmin', 'active', NOW(), NOW())
            ON CONFLICT (user_id, organization_id) DO NOTHING
            """,
            (str(uuid.uuid4()), row.user_id, row.org_id),
        )


def downgrade() -> None:
    # Irreversible on purpose: the inserted rows are not tagged, so deleting all
    # superadmin memberships would risk removing legitimate pre-existing data.
    return
