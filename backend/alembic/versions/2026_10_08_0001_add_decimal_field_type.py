"""Add the Decimal field type to the Field Library catalogue.

The engine has always stored `float` fields (money, percentages, hours), but
the catalogue had no code for them, so a decimal field could not be defined
in the Field Library and the legacy Form migration had nowhere to put one.
Decimal maps onto the engine's existing `float` type; nothing about storage
or validation changes.

An organization with no enablement rows sees every catalogue type. One that
has configured its types only sees the codes it enabled, so it gets Decimal
enabled alongside them rather than silently missing it.

Revision ID: 202610080001
Revises: 202609180001
Create Date: 2026-10-08
"""

from __future__ import annotations

import os

import sqlalchemy as sa

from alembic import op

revision = "202610080001"
down_revision = "202609180001"
branch_labels = None
depends_on = None

FIELD_TYPE_CODE = "decimal"
LABEL = "Decimal"
ENGINE_TYPE = "float"
SORT_ORDER = 55  # between Integer (50) and Date & Time (60)


def _definitions_schema() -> str:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return f"{app_schema}_definitions"


def upgrade() -> None:
    schema = _definitions_schema()
    op.execute(
        sa.text(
            f"""
            INSERT INTO "{schema}".field_type_catalogue
                (code, label, engine_type, config_kind, is_available, sort_order)
            VALUES (:code, :label, :engine_type, 'none', true, :sort_order)
            ON CONFLICT (code) DO UPDATE
            SET engine_type = EXCLUDED.engine_type, is_available = true
            """
        ).bindparams(
            code=FIELD_TYPE_CODE, label=LABEL, engine_type=ENGINE_TYPE, sort_order=SORT_ORDER
        )
    )
    op.execute(
        sa.text(
            f"""
            INSERT INTO "{schema}".organization_field_types (id, organization_id, field_type_code, enabled)
            SELECT gen_random_uuid()::text, configured.organization_id, :code, true
            FROM (SELECT DISTINCT organization_id FROM "{schema}".organization_field_types) AS configured
            WHERE NOT EXISTS (
                SELECT 1 FROM "{schema}".organization_field_types existing
                WHERE existing.organization_id = configured.organization_id
                  AND existing.field_type_code = :code
            )
            """
        ).bindparams(code=FIELD_TYPE_CODE)
    )


def downgrade() -> None:
    schema = _definitions_schema()
    op.execute(
        sa.text(
            f'DELETE FROM "{schema}".organization_field_types WHERE field_type_code = :code'
        ).bindparams(code=FIELD_TYPE_CODE)
    )
    op.execute(
        sa.text(f'DELETE FROM "{schema}".field_type_catalogue WHERE code = :code').bindparams(
            code=FIELD_TYPE_CODE
        )
    )
