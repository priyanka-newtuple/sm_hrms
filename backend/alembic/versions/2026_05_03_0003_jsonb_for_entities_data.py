"""Convert runtime.entities.data to JSONB and add GIN index.

The original migration 202605020005 created `runtime.entities.data` as
plain JSON (text-backed). The state-machine rewrite design calls for
JSONB so domain queries (`data @> '{"status":"active"}'`,
`data->>'email' = ?`) can use a GIN index. Now is the time to flip:
the table holds no production data on modular_backend.

Revision ID: 202605030003
Revises: 202605030002
Create Date: 2026-05-03
"""

from __future__ import annotations

import os

from alembic import op
import sqlalchemy as sa


revision = "202605030003"
down_revision = "202605030002"
branch_labels = None
depends_on = None


def _runtime_schema() -> str:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return f"{app_schema}_runtime"


def upgrade() -> None:
    runtime_schema = _runtime_schema()

    op.execute(
        sa.text(
            f'ALTER TABLE "{runtime_schema}".entities '
            f"ALTER COLUMN data TYPE JSONB USING data::jsonb"
        )
    )
    op.create_index(
        "ix_entities_data_gin",
        "entities",
        ["data"],
        postgresql_using="gin",
        schema=runtime_schema,
    )


def downgrade() -> None:
    runtime_schema = _runtime_schema()

    op.drop_index("ix_entities_data_gin", table_name="entities", schema=runtime_schema)
    op.execute(
        sa.text(
            f'ALTER TABLE "{runtime_schema}".entities '
            f"ALTER COLUMN data TYPE JSON USING data::json"
        )
    )
