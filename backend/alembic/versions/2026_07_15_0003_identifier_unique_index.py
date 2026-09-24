"""Dedupe entity identifiers and add a partial unique index.

STAT-353: templated identifiers rely on DB-enforced uniqueness of
(org, type, data->>'identifier'). Pre-existing duplicates get suffixed
_2, _3, ... (oldest row keeps the original value), repeating until no
suffixed value collides with another existing identifier.

Revision ID: 202607150003
Revises: 202607150002
Create Date: 2026-07-15 00:01:00
"""

from __future__ import annotations

import os

from alembic import op

revision = "202607150003"
down_revision = "202607150002"
branch_labels = None
depends_on = None


def _runtime_schema() -> str:
    return f"{os.environ.get('POSTGRES_APP_SCHEMA', 'public')}_runtime"


def upgrade() -> None:
    schema = _runtime_schema()
    # Dedupe: keep the oldest row per (org, type, identifier); suffix the rest.
    # A suffixed value can itself collide with a pre-existing `<base>_<n>` row,
    # so repeat until a pass renames nothing. Renamed values strictly grow each
    # pass, so this terminates; the cap only guards pathological data.
    dedupe_sql = f"""
        WITH ranked AS (
            SELECT entity_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY organization_id, entity_type_id, data->>'identifier'
                       ORDER BY created_at, entity_id
                   ) AS rn
            FROM {schema}.entities
            WHERE data->>'identifier' IS NOT NULL AND data->>'identifier' <> ''
        )
        UPDATE {schema}.entities e
        SET data = jsonb_set(
            e.data, '{{identifier}}',
            to_jsonb((e.data->>'identifier') || '_' || ranked.rn::text)
        )
        FROM ranked
        WHERE e.entity_id = ranked.entity_id AND ranked.rn > 1
        """
    conn = op.get_bind()
    for _ in range(20):
        renamed = conn.exec_driver_sql(dedupe_sql).rowcount
        if not renamed:
            break
        # Renames are user-visible (a live row can lose its identifier to an
        # older archived duplicate) — leave a trace in the migration output.
        print(f"identifier dedupe: renamed {renamed} duplicate identifier(s)")
    else:
        raise RuntimeError(
            "identifier dedupe did not converge after 20 passes — "
            "resolve duplicate identifiers manually, then re-run the migration"
        )
    op.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_runtime_entities_org_type_identifier
        ON {schema}.entities (organization_id, entity_type_id, (data->>'identifier'))
        WHERE data->>'identifier' IS NOT NULL AND data->>'identifier' <> ''
        """
    )


def downgrade() -> None:
    op.execute(
        f"DROP INDEX IF EXISTS {_runtime_schema()}.uq_runtime_entities_org_type_identifier"
    )
