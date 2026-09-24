"""add mcp capability registry

Revision ID: 202606230001
Revises: 202606180003
Create Date: 2026-06-23 00:00:00.000000
"""

import os

from alembic import op
import sqlalchemy as sa


revision = "202606230001"
down_revision = "202606180003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")

    op.create_table(
        "mcp_server_packages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("server_key", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("version", sa.String(length=64), nullable=False, server_default="1"),
        sa.Column("is_platform_managed", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        schema=schema,
    )
    op.create_index("ix_mcp_server_packages_server_key", "mcp_server_packages", ["server_key"], unique=True, schema=schema)

    op.create_table(
        "mcp_server_configurations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("server_package_id", sa.String(length=36), nullable=False),
        sa.Column("is_enabled", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("config_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(
            ["server_package_id"],
            [f"{schema}.mcp_server_packages.id"],
            ondelete="CASCADE",
        ),
        schema=schema,
    )
    op.create_index("ix_mcp_server_config_org_package", "mcp_server_configurations", ["organization_id", "server_package_id"], unique=True, schema=schema)

    op.create_table(
        "mcp_capabilities",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("server_package_id", sa.String(length=36), nullable=False),
        sa.Column("capability_key", sa.String(length=128), nullable=False),
        sa.Column("tool_id", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("input_schema", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("output_schema", sa.JSON(), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("default_requires_approval", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("default_is_mutating", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(
            ["server_package_id"],
            [f"{schema}.mcp_server_packages.id"],
            ondelete="CASCADE",
        ),
        schema=schema,
    )
    op.create_index("ix_mcp_capabilities_package_key", "mcp_capabilities", ["server_package_id", "capability_key"], unique=True, schema=schema)

    op.create_table(
        "mcp_capability_configurations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("capability_id", sa.String(length=36), nullable=False),
        sa.Column("is_enabled", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("requires_approval", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("config_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("integration_ref", sa.String(length=256), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(
            ["capability_id"],
            [f"{schema}.mcp_capabilities.id"],
            ondelete="CASCADE",
        ),
        schema=schema,
    )
    op.create_index("ix_mcp_capability_config_org_capability", "mcp_capability_configurations", ["organization_id", "capability_id"], unique=True, schema=schema)


def downgrade() -> None:
    schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    op.drop_index("ix_mcp_capability_config_org_capability", table_name="mcp_capability_configurations", schema=schema)
    op.drop_table("mcp_capability_configurations", schema=schema)
    op.drop_index("ix_mcp_capabilities_package_key", table_name="mcp_capabilities", schema=schema)
    op.drop_table("mcp_capabilities", schema=schema)
    op.drop_index("ix_mcp_server_config_org_package", table_name="mcp_server_configurations", schema=schema)
    op.drop_table("mcp_server_configurations", schema=schema)
    op.drop_index("ix_mcp_server_packages_server_key", table_name="mcp_server_packages", schema=schema)
    op.drop_table("mcp_server_packages", schema=schema)
