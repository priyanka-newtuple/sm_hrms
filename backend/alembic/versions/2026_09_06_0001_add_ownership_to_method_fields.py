"""Add ownership to method_library_method_version_fields.

The per-usage opt-in for method-block-level field inheritance. `'inherited'`
means: when this Method is pinned to a workflow state, resolve the field's value
from the record linked through the relation named by the row's EXISTING
`source_entity_type` / `source_field_key` columns (added in 202608300001, never
read by anything until now), instead of entering it directly.

No new `source` column on purpose. The row already carries three ways to say
"this value comes from elsewhere" — `source_entity_type` + `source_field_key`,
`inherit_from`, and now `ownership` — so this adds the one missing switch and
gives the dead pair its reader, rather than a fourth representation.

`inherit_from` and its publish-time projection into
`entity_type_relations.relation_metadata` are untouched. A row with
`ownership='inherited'` is deliberately NOT projected there: the whole point is
that it stays scoped to the Method Block that declared it, rather than being
escalated to every record of the entity type.

Values come from `workflow.models.interface.FieldOwnership` ('owned',
'inherited') so the word means the same thing on the method field as it does on
the resulting EntityField. NULL means "not stated" and behaves exactly as today.

Raw SQL and `IF NOT EXISTS` / `IF EXISTS` so re-running either direction is
harmless; the downgrade removes only what this revision added.

Revision ID: 202609060001
Revises: 202609010002
Create Date: 2026-09-06

Chain note: 202609010002 is the tracked head at the time of writing. Three
migrations dated 2026-09-05 exist in some working copies but are not yet
committed; once they land this revision and theirs will be two heads, and a
one-line `alembic merge` resolves it. Basing on an uncommitted revision was
rejected because the migration would then apply only where those files exist.
"""

from __future__ import annotations

import os

import sqlalchemy as sa

from alembic import op

revision = "202609060001"
down_revision = "202609010002"
branch_labels = None
depends_on = None

TABLE_NAME = "method_library_method_version_fields"
COLUMN_NAME = "ownership"
# Matches FieldOwnership's longest member with room to spare; kept in step with
# the model's OWNERSHIP_MAX_LENGTH.
COLUMN_LENGTH = 32


def _definitions_schema() -> str:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return f"{app_schema}_definitions"


def upgrade() -> None:
    schema = _definitions_schema()
    op.get_bind().execute(
        sa.text(
            f"""
            ALTER TABLE "{schema}".{TABLE_NAME}
            ADD COLUMN IF NOT EXISTS {COLUMN_NAME} VARCHAR({COLUMN_LENGTH}) NULL
            """
        )
    )


def downgrade() -> None:
    schema = _definitions_schema()
    op.get_bind().execute(
        sa.text(
            f"""
            ALTER TABLE "{schema}".{TABLE_NAME}
            DROP COLUMN IF EXISTS {COLUMN_NAME}
            """
        )
    )
