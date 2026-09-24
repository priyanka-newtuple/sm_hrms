"""Merge three independent Alembic heads into one.

202609050001 (the inherit_from chain-splice repair), the method-field
ownership schema change (202609060001), and the Kanban board-display-config
migration (202609030001) all branched off the same already-applied revision.
This no-op merge gives Alembic a single upgrade target again without
rewriting any branch's history.

(The two data-backfill migrations that used to sit under 202609050001 in
this branch's history - project_start_date and crm_account_region - are
standalone scripts now, under scripts/data_repairs/: they change specific
rows for two named organizations, not a table's structure, so they never
belonged in the schema-DDL chain. See design_docs/PROD_MIGRATION_RUNBOOK.md
step 4b.)

Revision ID: 202609070001
Revises: 202609050001, 202609060001, 202609030001
Create Date: 2026-09-07
"""

from __future__ import annotations


revision = "202609070001"
down_revision = ("202609050001", "202609060001", "202609030001")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Record the point where the independent histories converge."""


def downgrade() -> None:
    """Split the histories again when downgrading past this merge point."""

