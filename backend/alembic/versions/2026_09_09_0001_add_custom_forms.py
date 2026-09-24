"""Add the columns custom forms need.

`method_library_method_versions.connector_id` is the switch that makes a method
dynamic. A version with a connector and no field rows fetches a whole form from
that connector, per record, instead of contributing fields to the published
schema. Per version rather than per method on purpose: changing which connector
a method calls is a structural change, and versioning it is what stops an
already-published workflow silently starting to call somewhere else. No foreign
key to `connectors` — that table lives in the app schema while this one lives
in definitions; the manager checks the connector exists before storing the id.

`entities.custom_form_schema` and `entities.custom_form_data` split one form's
shape from its answers, because they have different writers. The schema is the
fetched structure, keyed by method id, since two dynamic methods can be pinned
to one state. The answers are one flat `{field_key: value}` map keyed by
`custom_forms.services.mapping.value_key` — flat so the results write-back and
a person editing a cell each write single keys instead of rewriting the whole
form and losing the other's work.

Neither belongs in `data`: that holds the fields the published schema declares,
and a custom form is fetched per record and declared nowhere.

Every column is nullable, so existing rows are untouched.

Revision ID: 202609090001
Revises: 202609070001
Create Date: 2026-09-09
"""

from __future__ import annotations

import os

import sqlalchemy as sa

from alembic import op

revision = "202609090001"
down_revision = "202609070001"
branch_labels = None
depends_on = None

METHOD_VERSIONS_TABLE = "method_library_method_versions"
CONNECTOR_COLUMN = "connector_id"
# Matches the identifier width used across that module's tables.
CONNECTOR_COLUMN_LENGTH = 36

ENTITIES_TABLE = "entities"
ENTITY_JSONB_COLUMNS = ("custom_form_schema", "custom_form_data")


def _definitions_schema() -> str:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return f"{app_schema}_definitions"


def _runtime_schema() -> str:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return f"{app_schema}_runtime"


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            f"""
            ALTER TABLE "{_definitions_schema()}".{METHOD_VERSIONS_TABLE}
            ADD COLUMN IF NOT EXISTS {CONNECTOR_COLUMN}
                VARCHAR({CONNECTOR_COLUMN_LENGTH}) NULL
            """
        )
    )
    for column in ENTITY_JSONB_COLUMNS:
        bind.execute(
            sa.text(
                f"""
                ALTER TABLE "{_runtime_schema()}".{ENTITIES_TABLE}
                ADD COLUMN IF NOT EXISTS {column} JSONB NULL
                """
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    for column in ENTITY_JSONB_COLUMNS:
        bind.execute(
            sa.text(
                f"""
                ALTER TABLE "{_runtime_schema()}".{ENTITIES_TABLE}
                DROP COLUMN IF EXISTS {column}
                """
            )
        )
    bind.execute(
        sa.text(
            f"""
            ALTER TABLE "{_definitions_schema()}".{METHOD_VERSIONS_TABLE}
            DROP COLUMN IF EXISTS {CONNECTOR_COLUMN}
            """
        )
    )
