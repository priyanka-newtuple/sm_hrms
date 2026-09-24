"""Clean invalid guard field references from published workflow definitions.

For each published workflow row (version >= 1), every guard in every transition
is inspected. Any guard that carries a 'field' key whose value is not present
in entity_schema.fields is removed from that transition. Guards without a
'field' key (role checks, policy checks, external checks) are left untouched.

This migration is idempotent: a second run finds no bad guards and updates
nothing. Downgrade is a no-op because removed guards cannot be recovered.

Revision ID: 202606010001
Revises: 202605280001
Create Date: 2026-06-01
"""

from __future__ import annotations

import json
import logging
import os

import sqlalchemy as sa
from alembic import op

revision = "202606010001"
down_revision = "202605290001"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")


def _app_schema() -> str:
    return os.environ.get("POSTGRES_APP_SCHEMA", "public")


def upgrade() -> None:
    app_schema = _app_schema()
    conn = op.get_bind()

    rows = conn.execute(
        sa.text(
            f"SELECT id, definition_json FROM {app_schema}.workflow_state_machines"
            f" WHERE version >= 1"
        )
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
                f"workflow guard migration: skipping row with unparseable JSON id={row_id}"
            )
            skipped += 1
            continue

        if not isinstance(definition, dict):
            logger.warning(
                f"workflow guard migration: skipping row with non-object definition id={row_id}"
            )
            skipped += 1
            continue

        schema_fields = definition.get("entity_schema", {}).get("fields", [])
        valid_field_names = {
            f["field"]
            for f in schema_fields
            if isinstance(f, dict) and "field" in f
        }

        transitions = definition.get("transitions", [])
        if not isinstance(transitions, list):
            continue

        changed = False
        for transition in transitions:
            if not isinstance(transition, dict):
                continue
            guards = transition.get("guards", [])
            if not isinstance(guards, list):
                continue

            cleaned = []
            for guard in guards:
                if not isinstance(guard, dict):
                    cleaned.append(guard)
                    continue
                field_ref = guard.get("field")
                if field_ref is not None and field_ref not in valid_field_names:
                    logger.warning(
                        f"workflow guard migration: removing guard with undefined field "
                        f"id={row_id} transition='{transition.get('key')}' field='{field_ref}'"
                    )
                    changed = True
                else:
                    cleaned.append(guard)

            transition["guards"] = cleaned

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
        f"workflow guard migration complete: "
        f"scanned={total} updated={updated} skipped={skipped}"
    )

    # --- Pass 2: seed terminal state + transition for blank skeleton workflows ---
    #
    # A skeleton workflow has version >= 1 (published), an empty transitions list,
    # and no state tagged "terminal". The only safe fix is to append a TERMINAL
    # state and one transition from the initial state to it.
    #
    # Safety conditions (ALL must hold before any row is touched):
    #   1. transitions list is present and empty — any existing transition means
    #      the workflow is partially built; do not touch it.
    #   2. No state carries the "terminal" tag — if one exists, nothing to fix.
    #   3. At least one state exists and an initial state can be identified.
    #   4. None of the candidate terminal state names collide with existing names.
    #
    # The migration is idempotent: on a second run every row already has a
    # terminal state and transitions, so condition 1 or 2 will be false and the
    # row is skipped.

    total2 = len(rows)
    updated2 = 0
    skipped2 = 0

    for row in rows:
        row_id = row[0]
        raw_json = row[1]

        try:
            definition = json.loads(raw_json)
        except (json.JSONDecodeError, TypeError):
            skipped2 += 1
            continue

        if not isinstance(definition, dict):
            skipped2 += 1
            continue

        states = definition.get("states", [])
        transitions = definition.get("transitions", [])

        if not isinstance(states, list) or not isinstance(transitions, list):
            skipped2 += 1
            continue

        # Condition 1: transitions must be completely empty.
        if len(transitions) > 0:
            continue

        # Condition 2: no terminal state must exist.
        has_terminal = any(
            isinstance(s, dict) and "terminal" in s.get("tags", [])
            for s in states
        )
        if has_terminal:
            continue

        # Condition 3: at least one state, and an initial state is identifiable.
        if len(states) == 0:
            logger.warning(
                f"workflow terminal migration: no states found, skipping id={row_id}"
            )
            skipped2 += 1
            continue

        initial_state_name = None
        for s in states:
            if isinstance(s, dict) and "initial" in s.get("tags", []):
                initial_state_name = s.get("name")
                break
        if initial_state_name is None:
            first = states[0]
            initial_state_name = first.get("name") if isinstance(first, dict) else None
        if not initial_state_name:
            logger.warning(
                f"workflow terminal migration: cannot identify initial state, skipping id={row_id}"
            )
            skipped2 += 1
            continue

        # Condition 4: find a terminal state name that does not collide.
        existing_names = {
            s["name"] for s in states if isinstance(s, dict) and "name" in s
        }
        terminal_name = None
        for candidate in ("TERMINAL", "CLOSED", "DONE", "COMPLETE", "FINISHED"):
            if candidate not in existing_names:
                terminal_name = candidate
                break
        if terminal_name is None:
            logger.warning(
                f"workflow terminal migration: all candidate terminal names collide, skipping id={row_id}"
            )
            skipped2 += 1
            continue

        max_order = max(
            (s.get("order", 0) for s in states if isinstance(s, dict)),
            default=0,
        )

        new_state = {
            "name": terminal_name,
            "description": "Terminal state.",
            "tags": ["terminal"],
            "order": max_order + 1,
        }

        transition_key = f"{initial_state_name.lower()}__to__{terminal_name.lower()}"
        new_transition = {
            "key": transition_key,
            "trigger": f"to_{terminal_name.lower()}",
            "label": f"Move to {terminal_name}",
            "from_state": initial_state_name,
            "to_state": terminal_name,
            "required_fields": [],
            "guards": [],
            "pre_transition_tasks": [],
            "post_transition_tasks": [],
            "auto_transition": None,
            "sla_seconds": None,
            "description": None,
        }

        definition["states"].append(new_state)
        definition["transitions"].append(new_transition)

        conn.execute(
            sa.text(
                f"UPDATE {app_schema}.workflow_state_machines"
                f" SET definition_json = :definition_json WHERE id = :id"
            ),
            {"definition_json": json.dumps(definition), "id": row_id},
        )
        updated2 += 1
        logger.info(
            f"workflow terminal migration: seeded state='{terminal_name}' "
            f"transition='{transition_key}' id={row_id}"
        )

    logger.info(
        f"workflow terminal migration complete: "
        f"scanned={total2} updated={updated2} skipped={skipped2}"
    )

    # --- Pass 3: fix initial_state pointing to a non-initial-tagged state ---
    #
    # When initial_state is set to a state name that does not carry the "initial"
    # tag, the dry-run simulation and the runtime enroll from different states.
    # The fix is to set initial_state to the state that IS tagged "initial".
    #
    # Safety conditions (ALL must hold before any row is touched):
    #   1. definition.initial_state is present and non-empty.
    #   2. The value of initial_state is NOT in the set of initial-tagged state names.
    #   3. Exactly one state carries the "initial" tag — if there are multiple,
    #      we pick the one with the lowest "order" value to be deterministic.
    #   4. At least one initial-tagged state exists (if none, it is a
    #      missing_initial_state problem; do not attempt to fix here).
    #
    # Idempotent: after fix, initial_state matches an initial-tagged state so
    # condition 2 is false on a second run and the row is skipped.

    total3 = len(rows)
    updated3 = 0
    skipped3 = 0

    for row in rows:
        row_id = row[0]
        raw_json = row[1]

        try:
            definition = json.loads(raw_json)
        except (json.JSONDecodeError, TypeError):
            skipped3 += 1
            continue

        if not isinstance(definition, dict):
            skipped3 += 1
            continue

        current_initial_state = definition.get("initial_state")
        if not current_initial_state or not isinstance(current_initial_state, str):
            continue

        states = definition.get("states", [])
        if not isinstance(states, list) or len(states) == 0:
            skipped3 += 1
            continue

        # Collect all states tagged "initial", sorted by order ascending.
        initial_tagged = [
            s for s in states
            if isinstance(s, dict) and "initial" in s.get("tags", []) and s.get("name")
        ]

        # Condition 4: at least one initial-tagged state must exist.
        if not initial_tagged:
            continue

        initial_tagged_names = {s["name"] for s in initial_tagged}

        # Condition 2: current initial_state must NOT already be correctly tagged.
        if current_initial_state in initial_tagged_names:
            continue

        # Pick the initial-tagged state with the lowest order (most deterministic).
        best = min(
            initial_tagged,
            key=lambda s: s.get("order", 0) if isinstance(s.get("order"), int) else 0,
        )
        correct_initial = best["name"]

        definition["initial_state"] = correct_initial

        conn.execute(
            sa.text(
                f"UPDATE {app_schema}.workflow_state_machines"
                f" SET definition_json = :definition_json WHERE id = :id"
            ),
            {"definition_json": json.dumps(definition), "id": row_id},
        )
        updated3 += 1
        logger.info(
            f"workflow initial_state migration: corrected initial_state "
            f"from='{current_initial_state}' to='{correct_initial}' id={row_id}"
        )

    logger.info(
        f"workflow initial_state migration complete: "
        f"scanned={total3} updated={updated3} skipped={skipped3}"
    )


def downgrade() -> None:
    # Pass 1: removed guards cannot be recovered.
    # Pass 2: seeded terminal states and transitions cannot be safely removed
    #         without knowing which rows were modified and what their prior state was.
    # Pass 3: prior incorrect initial_state values are not stored anywhere and
    #         cannot be recovered.
    # Downgrade is intentionally a no-op for all passes.
    pass
