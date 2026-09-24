"""Add workflow_services: the lookup table behind Workflow.service_id.

Mirrors method_library_categories exactly (2026_08_21_0003_add_method_library.py):
an organization-scoped lookup, unique by name case-insensitively, with a
composite (organization_id, id) unique constraint so a tenant-safe composite
foreign key can target it.

workflow_state_machines gets a nullable service_id column pointing at it, the
same shape as the category_id column on method_library_methods. Nullable and
no default: every existing row simply has no service until someone sets one
in workflow settings, and publish is never blocked by it being unset.

Revision ID: 202609010002
Revises: 202609010001
Create Date: 2026-09-01
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "202609010002"
down_revision = "202609010001"
branch_labels = None
depends_on = None

IDENTIFIER_LENGTH = 36
SERVICE_NAME_LENGTH = 256
TABLE_NAME = "workflow_services"


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
        sa.Column("name", sa.String(SERVICE_NAME_LENGTH), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_services"),
        sa.UniqueConstraint("organization_id", "id", name="uq_workflow_services_org_id"),
        schema=schema,
    )
    op.create_index(
        "uq_workflow_services_org_name",
        TABLE_NAME,
        ["organization_id", sa.text("lower(name)")],
        unique=True,
        schema=schema,
    )
    op.create_index(
        "ix_workflow_services_organization_id",
        TABLE_NAME,
        ["organization_id"],
        schema=schema,
    )

    # workflow_state_machines has no explicit schema of its own (resolves via
    # search_path, same as workflow_method_pins' FK back to it does).
    op.add_column(
        "workflow_state_machines",
        sa.Column("service_id", sa.String(IDENTIFIER_LENGTH), nullable=True),
        schema=app_schema,
    )
    op.create_index(
        "ix_workflow_state_machines_service_id",
        "workflow_state_machines",
        ["service_id"],
        schema=app_schema,
    )
    op.create_foreign_key(
        "fk_workflow_state_machines_service",
        source_table="workflow_state_machines",
        referent_table=TABLE_NAME,
        local_cols=["service_id", "organization_id"],
        remote_cols=["id", "organization_id"],
        source_schema=app_schema,
        referent_schema=schema,
    )


def downgrade() -> None:
    schema = _definitions_schema()
    app_schema = _app_schema()
    op.drop_constraint(
        "fk_workflow_state_machines_service",
        "workflow_state_machines",
        schema=app_schema,
        type_="foreignkey",
    )
    op.drop_index(
        "ix_workflow_state_machines_service_id",
        table_name="workflow_state_machines",
        schema=app_schema,
    )
    op.drop_column("workflow_state_machines", "service_id", schema=app_schema)
    op.drop_index("ix_workflow_services_organization_id", table_name=TABLE_NAME, schema=schema)
    op.drop_index("uq_workflow_services_org_name", table_name=TABLE_NAME, schema=schema)
    op.drop_table(TABLE_NAME, schema=schema)
