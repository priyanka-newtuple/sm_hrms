"""Add dashboard_definitions table for org-scoped customizable dashboards.

Stores one JSON config document per organization (keyed, default "primary")
that drives the metric-bound widget grid on the dashboard page.

Revision ID: 202606270001
Revises: 202606260001
Create Date: 2026-06-27
"""

from __future__ import annotations

import os

import sqlalchemy as sa

from alembic import op

revision = "202606270001"
down_revision = "202606260001"
branch_labels = None
depends_on = None

_app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "modular_backend")


def upgrade() -> None:
    op.create_table(
        "dashboard_definitions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            [f"{_app_schema}.organizations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "key",
            name="uq_dashboard_definitions_org_key",
        ),
        schema=_app_schema,
    )
    op.create_index(
        "ix_dashboard_definitions_organization_id",
        "dashboard_definitions",
        ["organization_id"],
        schema=_app_schema,
    )
    op.create_index(
        "ix_dashboard_definitions_key",
        "dashboard_definitions",
        ["key"],
        schema=_app_schema,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_dashboard_definitions_key",
        table_name="dashboard_definitions",
        schema=_app_schema,
    )
    op.drop_index(
        "ix_dashboard_definitions_organization_id",
        table_name="dashboard_definitions",
        schema=_app_schema,
    )
    op.drop_table("dashboard_definitions", schema=_app_schema)
