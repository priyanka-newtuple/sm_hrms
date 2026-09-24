"""Enforce one method pin per state per published workflow.

A state may reference a method once. Referencing it twice, especially at two
different versions, would merge fields from both into the schema and record two
pins, leaving the state describing a shape no single version of that method ever
had. ``State.method_refs`` rejects that input, and this constraint protects the
same rule for every database write path.

Revision ID: 202608220004
Revises: 202608220002
Create Date: 2026-08-22
"""

from __future__ import annotations

import os

import sqlalchemy as sa

from alembic import op

revision = "202608220004"
down_revision = "202608220002"
branch_labels = None
depends_on = None

TABLE_NAME = "workflow_method_pins"
CONSTRAINT_NAME = "uq_workflow_method_pins_machine_state_method"


def _definitions_schema() -> str:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return f"{app_schema}_definitions"


def upgrade() -> None:
    schema = _definitions_schema()
    # Collapse any duplicate rows before the constraint starts enforcing the
    # rule, retaining the newest pin per workflow row, state, and method.
    op.execute(
        sa.text(
            f"""
            DELETE FROM "{schema}".{TABLE_NAME} AS p
            USING "{schema}".{TABLE_NAME} AS newer
            WHERE p.workflow_state_machine_id = newer.workflow_state_machine_id
              AND p.state_key = newer.state_key
              AND p.method_id = newer.method_id
              AND (newer.created_at, newer.id) > (p.created_at, p.id)
            """
        )
    )
    op.create_unique_constraint(
        CONSTRAINT_NAME,
        TABLE_NAME,
        ["workflow_state_machine_id", "state_key", "method_id"],
        schema=schema,
    )


def downgrade() -> None:
    op.drop_constraint(
        CONSTRAINT_NAME, TABLE_NAME, schema=_definitions_schema(), type_="unique"
    )
