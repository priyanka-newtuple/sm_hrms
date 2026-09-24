"""Add picklists table for organisation-scoped dropdown option sets.

Revision ID: 202605050002
Revises: 202605050001
Create Date: 2026-05-05
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "202605050002"
down_revision = "202605050001"
branch_labels = None
depends_on = None


def _app_schema() -> str:
    return os.environ.get("POSTGRES_APP_SCHEMA", "public")


def upgrade() -> None:
    app_schema = _app_schema()

    op.create_table(
        "picklists",
        sa.Column("pk", sa.String(length=36), nullable=False),
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("options", JSONB, nullable=False, server_default="[]"),
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
        sa.PrimaryKeyConstraint("pk", name="pk_picklists"),
        sa.UniqueConstraint("organization_id", "id", name="uq_picklists_org_id"),
        schema=app_schema,
    )
    op.create_index(
        "ix_picklists_organization_id",
        "picklists",
        ["organization_id"],
        schema=app_schema,
    )


def downgrade() -> None:
    app_schema = _app_schema()
    op.drop_index("ix_picklists_organization_id", table_name="picklists", schema=app_schema)
    op.drop_table("picklists", schema=app_schema)
