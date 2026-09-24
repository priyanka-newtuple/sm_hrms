"""Add workflow_method_pins: which method version a workflow state pins.

One row per (published workflow row, state, method). The workflow row rather
than the workflow family, because publishing always writes a new row: each
published version keeps the pins it was built with, so republishing leaves the
previous version's pins readable rather than rewriting them.

The method foreign keys are composite with organization_id, the tenant-safe
pattern the method and field libraries already use, and carry no ON DELETE
clause on purpose. The database refusing to delete a pinned method is what backs
MethodLibraryModelService.delete_method's guard.

Revision ID: 202608220002
Revises: 202608220001
Create Date: 2026-08-22
"""

from __future__ import annotations

import os

import sqlalchemy as sa

from alembic import op

revision = "202608220002"
down_revision = "202608220001"
branch_labels = None
depends_on = None

IDENTIFIER_LENGTH = 36
STATE_KEY_LENGTH = 128
TABLE_NAME = "workflow_method_pins"


def _app_schema() -> str:
    return os.environ.get("POSTGRES_APP_SCHEMA", "public")


def _definitions_schema() -> str:
    return f"{_app_schema()}_definitions"


def upgrade() -> None:
    schema = _definitions_schema()
    app_schema = _app_schema()

    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.String(IDENTIFIER_LENGTH), nullable=False),
        sa.Column("organization_id", sa.String(IDENTIFIER_LENGTH), nullable=False),
        sa.Column(
            "workflow_state_machine_id", sa.String(IDENTIFIER_LENGTH), nullable=False
        ),
        sa.Column("state_key", sa.String(STATE_KEY_LENGTH), nullable=False),
        sa.Column("method_id", sa.String(IDENTIFIER_LENGTH), nullable=False),
        sa.Column("method_version_id", sa.String(IDENTIFIER_LENGTH), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_method_pins"),
        sa.ForeignKeyConstraint(
            ["workflow_state_machine_id"],
            [f"{app_schema}.workflow_state_machines.id"],
            name="fk_workflow_method_pins_state_machine",
            ondelete="CASCADE",
        ),
        # No ON DELETE: this is the guard that stops a pinned method being
        # deleted out from under a published workflow.
        sa.ForeignKeyConstraint(
            ["method_id", "organization_id"],
            [
                f"{schema}.method_library_methods.method_id",
                f"{schema}.method_library_methods.organization_id",
            ],
            name="fk_workflow_method_pins_method",
        ),
        sa.ForeignKeyConstraint(
            ["method_version_id", "organization_id"],
            [
                f"{schema}.method_library_method_versions.version_id",
                f"{schema}.method_library_method_versions.organization_id",
            ],
            name="fk_workflow_method_pins_method_version",
        ),
        schema=schema,
    )
    op.create_index(
        "ix_workflow_method_pins_machine_state",
        TABLE_NAME,
        ["workflow_state_machine_id", "state_key"],
        schema=schema,
    )
    op.create_index(
        "ix_workflow_method_pins_organization_id",
        TABLE_NAME,
        ["organization_id"],
        schema=schema,
    )
    op.create_index(
        "ix_workflow_method_pins_method_version_id",
        TABLE_NAME,
        ["method_version_id"],
        schema=schema,
    )


def downgrade() -> None:
    schema = _definitions_schema()
    op.drop_index(
        "ix_workflow_method_pins_method_version_id", table_name=TABLE_NAME, schema=schema
    )
    op.drop_index(
        "ix_workflow_method_pins_organization_id", table_name=TABLE_NAME, schema=schema
    )
    op.drop_index(
        "ix_workflow_method_pins_machine_state", table_name=TABLE_NAME, schema=schema
    )
    op.drop_table(TABLE_NAME, schema=schema)
