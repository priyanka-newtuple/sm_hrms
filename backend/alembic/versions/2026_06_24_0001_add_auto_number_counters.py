"""Add auto_number_counters table for sequential field ID generation.

Revision ID: 202606240001
Revises: 202606200001
Create Date: 2026-06-24
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "202606240001"
down_revision = "202606230001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = f"{os.environ.get('POSTGRES_APP_SCHEMA', 'public')}_runtime"
    op.create_table(
        "auto_number_counters",
        sa.Column("counter_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("entity_type_id", sa.String(36), nullable=False),
        sa.Column("field_key", sa.String(128), nullable=False),
        sa.Column("current_value", sa.Integer(), nullable=False, server_default="0"),
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
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("counter_id", name="pk_auto_number_counters"),
        sa.UniqueConstraint(
            "organization_id",
            "entity_type_id",
            "field_key",
            name="uq_auto_number_counters_org_type_field",
        ),
        schema=schema,
    )
    op.create_index(
        "ix_auto_number_counters_org_type",
        "auto_number_counters",
        ["organization_id", "entity_type_id"],
        schema=schema,
    )


def downgrade() -> None:
    schema = f"{os.environ.get('POSTGRES_APP_SCHEMA', 'public')}_runtime"
    op.drop_index(
        "ix_auto_number_counters_org_type",
        table_name="auto_number_counters",
        schema=schema,
    )
    op.drop_table("auto_number_counters", schema=schema)
