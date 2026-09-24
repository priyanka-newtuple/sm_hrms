"""Drop the legacy workflow + entity tables (Wave 2 schema cleanup).

Wave 1 cut over the workflow runtime to:
- runtime.entities, runtime.entity_state, runtime.entity_relations
- audit.entity_events, audit.transition_attempts

The legacy app-schema tables `entities`, `entity_state`, `entity_relations`,
`workflow_entity_states`, and `workflow_activity_log` were TRUNCATEd in
2026_05_03_0005 but kept in place so the conversion script could read them
and so we could roll back if anything went wrong. After a soak period on
the new model they are unused and the corresponding ORM classes are gone
in the same wave 2 PR.

Note: legacy `entity_events` is NOT dropped — auth/log_auth_event still
writes there. Porting the auth audit log to a dedicated audit.auth_events
table is tracked separately.

Revision ID: 202605040001
Revises: 202605030005
Create Date: 2026-05-04
"""

from __future__ import annotations

import os

from alembic import op
from sqlalchemy import inspect


revision = "202605040001"
down_revision = "202605030005"
branch_labels = None
depends_on = None


_LEGACY_TABLES = (
    "workflow_activity_log",
    "workflow_entity_states",
    "entity_state",
    "entity_relations",
    "entities",
)


def _app_schema() -> str:
    return os.environ.get("POSTGRES_APP_SCHEMA", "public")


def upgrade() -> None:
    schema = _app_schema()
    bind = op.get_bind()
    existing = set(inspect(bind).get_table_names(schema=schema))
    for table in _LEGACY_TABLES:
        if table in existing:
            op.drop_table(table, schema=schema)


def downgrade() -> None:
    # Recreating these tables empty would be feasible but the data is gone
    # by construction of this migration chain. Roll back via DB restore.
    pass
