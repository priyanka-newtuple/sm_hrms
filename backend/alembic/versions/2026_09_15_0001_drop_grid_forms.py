"""Drop the grid form tables.

The grid_forms module is removed: custom_forms covers the same ground, fetching
a form per record from a connector. Nothing reads these tables any more.

Revision ID: 202609150001
Revises: 202609090001
Create Date: 2026-09-15 00:01:00
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "202609150001"
down_revision = "202609090001"
branch_labels = None
depends_on = None


def _definitions_schema() -> str:
    return f"{os.environ.get('POSTGRES_APP_SCHEMA', 'public')}_definitions"


def _runtime_schema() -> str:
    return f"{os.environ.get('POSTGRES_APP_SCHEMA', 'public')}_runtime"


def upgrade() -> None:
    op.drop_index(
        "ix_grid_form_instances_org_entity",
        table_name="grid_form_instances",
        schema=_runtime_schema(),
    )
    op.drop_table("grid_form_instances", schema=_runtime_schema())
    op.drop_index(
        "ix_grid_form_templates_org_entity_type",
        table_name="grid_form_templates",
        schema=_definitions_schema(),
    )
    op.drop_table("grid_form_templates", schema=_definitions_schema())


def downgrade() -> None:
    """Recreate both tables empty. The rows the upgrade dropped do not come back."""
    op.create_table(
        "grid_form_templates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("entity_type", sa.String(128), nullable=False),
        sa.Column("fetch_url", sa.Text(), nullable=False),
        sa.Column("fetch_method", sa.String(8), nullable=False, server_default="GET"),
        sa.Column("auth_type", sa.String(16), nullable=False, server_default="none"),
        sa.Column("auth_config", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("encrypted_auth_secret", sa.Text(), nullable=True),
        sa.Column("secret_hint", sa.String(32), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_edited_by", sa.String(128), nullable=True),
        sa.Column(
            "last_edited_fields", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema=_definitions_schema(),
    )
    op.create_index(
        "ix_grid_form_templates_org_entity_type",
        "grid_form_templates",
        ["organization_id", "entity_type"],
        schema=_definitions_schema(),
    )
    op.create_table(
        "grid_form_instances",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("template_id", sa.String(36), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("data", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("state_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_edited_by", sa.String(128), nullable=True),
        sa.Column(
            "last_edited_fields", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "template_id", "entity_id", name="uq_grid_form_instances_template_entity"
        ),
        schema=_runtime_schema(),
    )
    op.create_index(
        "ix_grid_form_instances_org_entity",
        "grid_form_instances",
        ["organization_id", "entity_id"],
        schema=_runtime_schema(),
    )
