"""Add reply threading and likes to comments.

Adds:
  - parent_id: self-referential FK, nullable. NULL = top-level comment;
    set = single-level reply to that comment. Depth beyond one level is
    enforced in the manager, not the schema.
  - likes: JSONB array of {user_id, user_name, user_avatar_url, liked_at},
    same denormalized shape already used for author_name/author_avatar_url
    on this table, so "who liked this" needs no extra lookup or join.

Revision ID: 202608140001
Revises: 202608050001
Create Date: 2026-08-14
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "202608140001"
down_revision = "202608050001"
branch_labels = None
depends_on = None


def _runtime_schema() -> str:
    return os.environ.get("POSTGRES_APP_SCHEMA", "public") + "_runtime"


def upgrade() -> None:
    schema = _runtime_schema()

    op.add_column(
        "comments",
        sa.Column("parent_id", sa.String(length=36), nullable=True),
        schema=schema,
    )
    op.add_column(
        "comments",
        sa.Column("likes", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        schema=schema,
    )
    op.create_foreign_key(
        "fk_comments_parent_id",
        "comments",
        "comments",
        ["parent_id"],
        ["id"],
        source_schema=schema,
        referent_schema=schema,
        ondelete="CASCADE",
    )
    op.create_index("ix_comments_parent_id", "comments", ["parent_id"], schema=schema)


def downgrade() -> None:
    schema = _runtime_schema()

    op.drop_index("ix_comments_parent_id", table_name="comments", schema=schema)
    op.drop_constraint("fk_comments_parent_id", "comments", schema=schema, type_="foreignkey")
    op.drop_column("comments", "likes", schema=schema)
    op.drop_column("comments", "parent_id", schema=schema)
