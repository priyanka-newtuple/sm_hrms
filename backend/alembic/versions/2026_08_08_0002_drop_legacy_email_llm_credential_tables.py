"""Drop legacy credential tables email_configs and llm_api_keys.

These stores are superseded by organization_integrations. The preceding
revision (202608080001) backfilled any residual rows into that table, so the
legacy tables are now safe to remove. downgrade() recreates the table schemas
(structure only — data is not restored).

Revision ID: 202608080002
Revises: 202608080001
Create Date: 2026-08-08
"""

from __future__ import annotations

import os

import sqlalchemy as sa

from alembic import op

revision = "202608080002"
down_revision = "202608080001"
branch_labels = None
depends_on = None

_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")


def upgrade() -> None:
    op.drop_table("email_configs", schema=_schema)
    op.drop_table("llm_api_keys", schema=_schema)


def downgrade() -> None:
    op.create_table(
        "email_configs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("encrypted_access_key_id", sa.Text(), nullable=False),
        sa.Column("encrypted_secret_key", sa.Text(), nullable=False),
        sa.Column("access_key_hint", sa.String(length=32), nullable=True),
        sa.Column("region", sa.String(length=32), nullable=True),
        sa.Column("smtp_host", sa.String(length=256), nullable=True),
        sa.Column("smtp_port", sa.Integer(), nullable=True),
        sa.Column("smtp_use_tls", sa.Boolean(), nullable=True),
        sa.Column("from_email", sa.String(length=256), nullable=False),
        sa.Column("from_name", sa.String(length=128), nullable=True),
        sa.Column("reply_to_email", sa.String(length=256), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("validation_status", sa.String(length=16), nullable=True),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("acs_endpoint", sa.String(length=256), nullable=True),
        sa.Column("encrypted_connection_string", sa.Text(), nullable=True),
        sa.Column("connection_string_hint", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"], [f"{_schema}.organizations.id"], ondelete="CASCADE"
        ),
        schema=_schema,
    )
    op.create_index(
        "ix_email_configs_org_provider",
        "email_configs",
        ["organization_id", "provider"],
        unique=True,
        schema=_schema,
    )
    op.create_index(
        "ix_email_configs_organization_id",
        "email_configs",
        ["organization_id"],
        schema=_schema,
    )

    op.create_table(
        "llm_api_keys",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("encrypted_key", sa.Text(), nullable=False),
        sa.Column("display_hint", sa.String(length=32), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("validation_status", sa.String(length=16), nullable=True),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], [f"{_schema}.organizations.id"], ondelete="CASCADE"
        ),
        schema=_schema,
    )
    op.create_index(
        "ix_llm_api_keys_org_provider",
        "llm_api_keys",
        ["organization_id", "provider"],
        unique=True,
        schema=_schema,
    )
