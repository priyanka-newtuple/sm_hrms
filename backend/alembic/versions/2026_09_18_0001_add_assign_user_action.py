"""Add the workflow action that assigns a record to a user or its originator.

Must ship together with the `entity.assign_user` executor registration: the
catalogue row is what lets an author pick the action in the builder, and the
executor is what lets the worker run it.

Revision ID: 202609180001
Revises: 202609170001
Create Date: 2026-09-18 00:01:00
"""

from __future__ import annotations

import os

import sqlalchemy as sa

from alembic import op

revision = "202609180001"
down_revision = "202609170001"
branch_labels = None
depends_on = None

# Fixed so a re-run collides on the primary key and does nothing, rather than
# seeding a second copy of the same action.
_DEFINITION_ID = "0575406f-d631-4052-8888-34308dc95158"


def _definitions_schema() -> str:
    return f"{os.environ.get('POSTGRES_APP_SCHEMA', 'public')}_definitions"


def upgrade() -> None:
    schema = _definitions_schema()
    op.execute(
        sa.text(
            f'''INSERT INTO "{schema}".action_definitions
                (definition_id, organization_id, kind, name, description,
                 input_schema, output_schema, is_internal)
            VALUES (
                '{_DEFINITION_ID}', NULL,
                'entity.assign_user', 'User Assignment',
                'Assign the record to a selected user, or to the person who created it.',
                '{{"assignment_type": {{"type": "string", "enum": ["user", "originator"]}},
                  "user_id": {{"type": "string"}}}}'::jsonb,
                '{{"outcome": {{"type": "string", "enum": ["assigned", "already_assigned",
                  "originator_not_found", "user_not_found", "user_suspended"]}}}}'::jsonb,
                FALSE
            ) ON CONFLICT DO NOTHING'''
        )
    )


def downgrade() -> None:
    schema = _definitions_schema()
    op.execute(
        sa.text(
            f'''DELETE FROM "{schema}".action_definitions
                WHERE definition_id = '{_DEFINITION_ID}' '''
        )
    )
