"""Scope the identifier unique index to non-archived rows.

STAT-418: identifiers were reserved forever, even after the record was
archived (soft-deleted) — the unique index spanned every row regardless of
archived_at. Rebuild it as a partial index over active rows only, so an
archived record's identifier becomes reusable.

Revision ID: 202607210001
Revises: 202607170006
Create Date: 2026-07-21 00:01:00
"""

from __future__ import annotations

import os

from alembic import op

revision = "202607210001"
down_revision = "202607170006"
branch_labels = None
depends_on = None


def _runtime_schema() -> str:
    return f"{os.environ.get('POSTGRES_APP_SCHEMA', 'public')}_runtime"


def upgrade() -> None:
    schema = _runtime_schema()
    op.execute(f"DROP INDEX IF EXISTS {schema}.uq_runtime_entities_org_type_identifier")
    op.execute(
        f"""
        CREATE UNIQUE INDEX uq_runtime_entities_org_type_identifier
        ON {schema}.entities (organization_id, entity_type_id, (data->>'identifier'))
        WHERE data->>'identifier' IS NOT NULL AND data->>'identifier' <> ''
              AND archived_at IS NULL
        """
    )


def downgrade() -> None:
    schema = _runtime_schema()
    op.execute(f"DROP INDEX IF EXISTS {schema}.uq_runtime_entities_org_type_identifier")
    op.execute(
        f"""
        CREATE UNIQUE INDEX uq_runtime_entities_org_type_identifier
        ON {schema}.entities (organization_id, entity_type_id, (data->>'identifier'))
        WHERE data->>'identifier' IS NOT NULL AND data->>'identifier' <> ''
        """
    )
