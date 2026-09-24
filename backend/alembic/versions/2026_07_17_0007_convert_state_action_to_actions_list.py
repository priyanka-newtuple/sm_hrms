"""Convert each state's `on_state_action` to the `on_state_actions` list.

Covers every row in workflow_state_machines — published (version >= 1) and
draft (version = 0) — since both are stored as JSON blobs in the same table.
A state with a legacy singular `on_state_action` gets `on_state_actions`
set to a one-item list built from it, and the old key is dropped. A state
that already has `on_state_actions` (or neither key) is left untouched
beyond removing the stale `on_state_action` key if present.

Idempotent: a second run finds no `on_state_action` keys left and updates
nothing. Downgrade is a no-op — this is a shape migration, not a data loss
risk, and reversing it would require guessing which action was "the" one
if a state ever gains more than one.

Revision ID: 202607170007
Revises: 202607210001
Create Date: 2026-07-17
"""

from __future__ import annotations

import json
import logging
import os

import sqlalchemy as sa
from alembic import op

revision = "202607170007"
down_revision = "202607210001"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")


def _app_schema() -> str:
    return os.environ.get("POSTGRES_APP_SCHEMA", "public")


def upgrade() -> None:
    app_schema = _app_schema()
    conn = op.get_bind()

    rows = conn.execute(
        sa.text(f"SELECT id, definition_json FROM {app_schema}.workflow_state_machines")
    ).fetchall()

    total = len(rows)
    updated = 0
    skipped = 0

    for row in rows:
        row_id = row[0]
        raw_json = row[1]

        try:
            definition = json.loads(raw_json)
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                f"state_actions migration: skipping row with unparseable JSON id={row_id}"
            )
            skipped += 1
            continue

        if not isinstance(definition, dict):
            skipped += 1
            continue

        states = definition.get("states", [])
        if not isinstance(states, list):
            continue

        changed = False
        for state in states:
            if not isinstance(state, dict) or "on_state_action" not in state:
                continue
            legacy = state.pop("on_state_action")
            if legacy is not None and not state.get("on_state_actions"):
                state["on_state_actions"] = [legacy]
            changed = True

        if changed:
            conn.execute(
                sa.text(
                    f"UPDATE {app_schema}.workflow_state_machines"
                    f" SET definition_json = :definition_json WHERE id = :id"
                ),
                {"definition_json": json.dumps(definition), "id": row_id},
            )
            updated += 1

    logger.info(
        f"state_actions migration complete: scanned={total} updated={updated} skipped={skipped}"
    )


def downgrade() -> None:
    # Shape-only migration; the legacy single-action key carried no data that
    # the list form doesn't also carry. Reversing would require guessing
    # which action to keep if a state ever gains more than one.
    pass
