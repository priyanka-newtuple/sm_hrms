"""Seed version-0 draft rows for workflow families that have none.

For every (organization_id, machine_name) pair that has at least one published
row (version >= 1) but no draft row (version = 0), inserts a blank version-0
draft so the frontend can open and edit the workflow.

Identity columns (organization_id, machine_key, machine_name, entity_type) are
taken from the latest published version of each family. definition_json is a
blank starter template — not a copy of the published definition. canvas_metadata
is left NULL.

This migration is idempotent: a second run finds no families missing a draft
and inserts nothing. Downgrade is a no-op because the inserted rows can simply
be left in place without causing harm.

Revision ID: 202606010002
Revises: 202606010001
Create Date: 2026-06-01
"""

from __future__ import annotations

import json
import logging
import os
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "202606010002"
down_revision = "202606010001"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")


def _app_schema() -> str:
    return os.environ.get("POSTGRES_APP_SCHEMA", "public")


def _blank_definition(machine_key: str) -> str:
    """Return a minimal blank draft definition JSON string."""
    return json.dumps({
        "machine_key": machine_key,
        "name": "New Workflow",
        "description": "",
        "entity_type": "entity",
        "entity_schema": {"entity_type": "entity", "fields": []},
        "states": [
            {
                "name": "INITIAL",
                "description": "Initial state.",
                "tags": ["initial"],
                "order": 1,
            }
        ],
        "initial_state": "INITIAL",
        "transitions": [],
    })


def upgrade() -> None:
    app_schema = _app_schema()
    table = f"{app_schema}.workflow_state_machines"
    conn = op.get_bind()

    # Find all (organization_id, machine_name) pairs that have published rows
    # but no version-0 draft row.
    missing = conn.execute(sa.text(f"""
        SELECT DISTINCT organization_id, machine_name
        FROM {table}
        WHERE version >= 1
          AND (organization_id, machine_name) NOT IN (
              SELECT organization_id, machine_name
              FROM {table}
              WHERE version = 0
          )
    """)).fetchall()

    if not missing:
        logger.info("workflow draft seed migration: no families missing a draft row, nothing to do")
        return

    inserted = 0
    for org_id, machine_name in missing:
        # Get the latest published row for identity columns.
        latest = conn.execute(sa.text(f"""
            SELECT machine_key, entity_type
            FROM {table}
            WHERE organization_id = :org_id
              AND machine_name = :machine_name
              AND version >= 1
            ORDER BY version DESC
            LIMIT 1
        """), {"org_id": org_id, "machine_name": machine_name}).fetchone()

        if latest is None:
            continue

        machine_key = latest[0]
        entity_type = latest[1]
        new_id = str(uuid4())

        conn.execute(sa.text(f"""
            INSERT INTO {table}
              (id, organization_id, machine_key, machine_name, description,
               entity_type, version, is_active, definition_json, canvas_metadata_json)
            VALUES
              (:id, :organization_id, :machine_key, :machine_name, NULL,
               :entity_type, 0, false, :definition_json, NULL)
        """), {
            "id": new_id,
            "organization_id": org_id,
            "machine_key": machine_key,
            "machine_name": machine_name,
            "entity_type": entity_type,
            "definition_json": _blank_definition(machine_key),
        })

        logger.info(
            f"workflow draft seed migration: inserted draft "
            f"id={new_id} org={org_id} machine={machine_name}"
        )
        inserted += 1

    logger.info(
        f"workflow draft seed migration complete: "
        f"families_found={len(missing)} inserted={inserted}"
    )


def downgrade() -> None:
    # Inserted draft rows are harmless to leave in place.
    # Downgrade is intentionally a no-op.
    pass
