"""Backfill user_organizations rows for users whose primary org has no membership row.

The OAuth and local signup paths historically only set users.organization_id
without writing a user_organizations row. Without that row the org switcher
cannot list (or return to) the org, while the add-user duplicate check and
token minting still treat the user as a member — leaving them stuck as an
invisible member after switching orgs.

This migration is idempotent — a NOT EXISTS guard plus ON CONFLICT skip rows
that already exist. Safe to re-run.

Revision ID: 202607080001
Revises: 202607030001
Create Date: 2026-07-08
"""

from __future__ import annotations

import os
import uuid

from alembic import op


revision = "202607080001"
down_revision = "202607030001"
branch_labels = None
depends_on = None


def _schema() -> str:
    return os.environ.get("POSTGRES_APP_SCHEMA", "public")


def upgrade() -> None:
    schema = _schema()
    conn = op.get_bind()

    rows = conn.exec_driver_sql(
        f"""
        SELECT u.id AS user_id, u.organization_id AS org_id, u.role AS role
        FROM "{schema}".users u
        WHERE u.organization_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM "{schema}".user_organizations uo
              WHERE uo.user_id = u.id
                AND uo.organization_id = u.organization_id
          )
        """
    ).fetchall()

    if not rows:
        return

    for row in rows:
        conn.exec_driver_sql(
            f"""
            INSERT INTO "{schema}".user_organizations
                (id, user_id, organization_id, role, status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, 'active', NOW(), NOW())
            ON CONFLICT (user_id, organization_id) DO NOTHING
            """,
            (str(uuid.uuid4()), row.user_id, row.org_id, row.role or "viewer"),
        )


def downgrade() -> None:
    # Irreversible on purpose: the inserted rows are not tagged, so deleting
    # them wholesale would risk removing legitimate pre-existing memberships.
    return
