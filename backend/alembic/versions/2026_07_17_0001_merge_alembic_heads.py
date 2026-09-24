"""Merge two alembic heads that independently branched from 202607150003.

`202607150004` (entity field permission filter — read-condition columns on
role_permissions, STAT-358) and `202607160003` (allow duplicate file uploads)
were developed in parallel PRs, each correctly chaining off the then-current
head, but neither PR rebased onto the other before merging — so both landed
on `main` as siblings once merged, rather than a single line. This is a
no-op merge migration: it makes no schema changes of its own, and does not
alter either existing migration's `revision`/`down_revision` (both are
already merged and may already be applied in other environments — rewriting
either one's identity here would orphan any `alembic_version` table that
already recorded it). It only adds one more step both chains converge into.

Revision ID: 202607170001
Revises: 202607150004, 202607160003
Create Date: 2026-07-17 00:01:00
"""

from __future__ import annotations

revision = "202607170001"
down_revision = ("202607150004", "202607160003")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
