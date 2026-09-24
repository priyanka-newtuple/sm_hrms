"""Wipe legacy workflow data rows after the new state-machine cutover.

The workflow manager and projections reader now read/write through
runtime.entities / runtime.entity_state / runtime.entity_relations /
audit.entity_events / audit.transition_attempts. The legacy tables
`entities`, `entity_state`, `entity_relations`, and the workflow-side
`workflow_entity_states` / `workflow_activity_log` are no longer written
to and stale rows would only confuse projection rebuilds and ad-hoc
queries.

This migration TRUNCATES (not drops) the legacy rows. The tables and
ORM classes stay in place because:
- the conversion script in `backend/scripts/convert_legacy_workflow_states.py`
  reads from them and must be runnable before this wipe is applied
- dropping the tables is reserved for a Wave 2 cleanup once we are
  certain nothing reads them

Operators must run the conversion script first if they have legacy data
worth keeping; this migration cannot be safely re-run after a wipe.

Revision ID: 202605030005
Revises: 202605030004
Create Date: 2026-05-03
"""

from __future__ import annotations

from alembic import op


revision = "202605030005"
down_revision = "202605030004"
branch_labels = None
depends_on = None


_LEGACY_TABLES = (
    "entities",
    "entity_state",
    "entity_relations",
    "workflow_entity_states",
    "workflow_activity_log",
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = __import__("sqlalchemy").inspect(bind)
    existing = set(inspector.get_table_names())
    targets = [t for t in _LEGACY_TABLES if t in existing]
    if not targets:
        return
    table_list = ", ".join(targets)
    op.execute(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE")


def downgrade() -> None:
    # Wiped data cannot be recovered from a downgrade. The reverse step is
    # to re-run the conversion script against any retained legacy backup.
    pass
