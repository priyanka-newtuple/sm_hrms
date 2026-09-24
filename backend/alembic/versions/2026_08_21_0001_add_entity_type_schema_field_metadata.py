"""Add per-form field behaviour to the form-to-field-library link.

Structural only, no backfill. Holds required, nullable, default, ownership,
source, editable, col_span, placeholder and a label override for one field on
one form.

Revision ID: 202608210001
Revises: 202608190001
Create Date: 2026-08-21
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "202608210001"
down_revision = "202608190001"
branch_labels = None
depends_on = None

# ── Note for whoever writes the forms-to-field-library backfill ───────────────
# That migration will live in this directory, and it must also populate this
# `metadata` column on every link row it creates, using the same required /
# nullable / default / ownership / source / editable / col_span / placeholder
# values it already reads off the old inline field to build the library version's
# `settings`. Migrated links need to be self-sufficient from the start: nothing
# falls back to `settings` for per-form behaviour, so a link left with an empty
# metadata object would silently lose all of it.


def _definitions_schema() -> str:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return f"{app_schema}_definitions"


def upgrade() -> None:
    op.add_column(
        "entity_type_schema_fields",
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=True,
        ),
        schema=_definitions_schema(),
    )


def downgrade() -> None:
    op.drop_column(
        "entity_type_schema_fields", "metadata", schema=_definitions_schema()
    )
