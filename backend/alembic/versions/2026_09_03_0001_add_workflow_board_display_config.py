"""Add workflow_board_display_configs: per-workflow Kanban card field selection.

Kanban cards can show up to 3 admin-configured extra entity fields. The
selection is scoped to `(organization_id, machine_name)` — deliberately
independent of the versioned `workflow_state_machines` rows, so it applies
immediately (no draft/publish step) and doesn't need to be copied forward
every time a workflow is republished.

Revision ID: 202609030001
Revises: 202608290001
Create Date: 2026-09-03
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "202609030001"
down_revision = "202608290001"
branch_labels = None
depends_on = None

IDENTIFIER_LENGTH = 36
MACHINE_NAME_LENGTH = 128


def upgrade() -> None:
    schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")

    op.create_table(
        "workflow_board_display_configs",
        sa.Column("id", sa.String(IDENTIFIER_LENGTH), nullable=False),
        sa.Column("organization_id", sa.String(IDENTIFIER_LENGTH), nullable=False),
        sa.Column("machine_name", sa.String(MACHINE_NAME_LENGTH), nullable=False),
        sa.Column(
            "fields_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("updated_by", sa.String(IDENTIFIER_LENGTH), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_board_display_configs"),
        schema=schema,
    )
    # Serves every (organization_id, ...) and (organization_id, machine_name)
    # lookup via its leading column — a separate single-column index on
    # organization_id alone would be redundant with this one.
    op.create_index(
        "uq_workflow_board_display_config_org_machine",
        "workflow_board_display_configs",
        ["organization_id", "machine_name"],
        unique=True,
        schema=schema,
    )
    op.create_index(
        "ix_workflow_board_display_configs_machine_name",
        "workflow_board_display_configs",
        ["machine_name"],
        schema=schema,
    )


def downgrade() -> None:
    schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    for index_name in (
        "ix_workflow_board_display_configs_machine_name",
        "uq_workflow_board_display_config_org_machine",
    ):
        op.drop_index(index_name, table_name="workflow_board_display_configs", schema=schema)
    op.drop_table("workflow_board_display_configs", schema=schema)
