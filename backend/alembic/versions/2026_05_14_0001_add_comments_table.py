"""Add comments table with structured mentions and state context.

Replaces the in-memory comment store in CommunicationsModelService with
a proper DB-backed table. Supports:
  - entity-level comments (workflow_id/state_id/state_name all null)
  - workflow-state-scoped comments (optional FK to runtime.entity_state)
  - structured JSONB mentions: [{user_id, full_name, position}]
  - append-only edit_history: [{previous_text, edited_at, edited_by_id, edited_by_name}]
  - soft delete via archived_at

Revision ID: 202605140001
Revises: 202605170001
Create Date: 2026-05-14
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision = "202605140001"
down_revision = "202605130001"
branch_labels = None
depends_on = None


def _schemas() -> tuple[str, str]:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return app_schema, f"{app_schema}_runtime"


def upgrade() -> None:
    app_schema, runtime_schema = _schemas()

    op.create_table(
        "comments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=128), nullable=False),
        # state context — all nullable; workflow_id is a plain column (no FK until
        # workflow table rename lands in Wave 2)
        sa.Column("workflow_id", sa.String(length=36), nullable=True),
        sa.Column("state_id", sa.String(length=36), nullable=True),
        sa.Column("state_name", sa.String(length=128), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("mentions", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("edit_history", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("author_id", sa.String(length=36), nullable=True),
        sa.Column("author_name", sa.String(length=256), nullable=False),
        sa.Column("author_role", sa.String(length=64), nullable=True),
        sa.Column("author_avatar_url", sa.String(length=2048), nullable=True),
        sa.Column("visibility", sa.String(length=32), nullable=False, server_default=sa.text("'all'")),
        sa.Column("visible_to_roles", JSONB, nullable=True),
        sa.Column("is_edited", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_comments"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            [f"{app_schema}.organizations.id"],
            ondelete="CASCADE",
            name="fk_comments_organization_id",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            [f"{app_schema}.users.id"],
            ondelete="SET NULL",
            name="fk_comments_author_id",
        ),
        sa.ForeignKeyConstraint(
            ["state_id"],
            [f"{runtime_schema}.entity_state.state_id"],
            ondelete="SET NULL",
            name="fk_comments_state_id",
        ),
        schema=runtime_schema,
    )

    op.create_index(
        "ix_comments_entity_org",
        "comments",
        ["entity_id", "organization_id"],
        schema=runtime_schema,
    )
    op.create_index(
        "ix_comments_entity_workflow_state",
        "comments",
        ["entity_id", "workflow_id", "state_id"],
        schema=runtime_schema,
    )
    op.create_index("ix_comments_active", "comments", ["entity_id", "archived_at"], schema=runtime_schema)
    op.create_index("ix_comments_author", "comments", ["author_id"], schema=runtime_schema)
    op.create_index("ix_comments_created", "comments", ["created_at"], schema=runtime_schema)


def downgrade() -> None:
    _app_schema, runtime_schema = _schemas()
    op.drop_index("ix_comments_created", table_name="comments", schema=runtime_schema)
    op.drop_index("ix_comments_author", table_name="comments", schema=runtime_schema)
    op.drop_index("ix_comments_active", table_name="comments", schema=runtime_schema)
    op.drop_index("ix_comments_entity_workflow_state", table_name="comments", schema=runtime_schema)
    op.drop_index("ix_comments_entity_org", table_name="comments", schema=runtime_schema)
    op.drop_table("comments", schema=runtime_schema)