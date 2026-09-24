"""Tighten runtime.entities FK to be org-scoped.

Closes a tenant-isolation gap: the original FK on
runtime.entities.entity_type_id only validated the type_id existed,
not that it belonged to the same organization as the entity row.
A caller in org-A who knew an entity_type_id UUID owned by org-B
could attach a record to that cross-org type.

Fix: replace the single-column FK with a composite FK on
(organization_id, entity_type_id) -> entity_types(organization_id,
entity_type_id). Requires adding a UNIQUE constraint on
(organization_id, entity_type_id) in entity_types so the FK target
is well-defined.

Revision ID: 202605030001
Revises: 202605020005
Create Date: 2026-05-03
"""

from __future__ import annotations

import os

from alembic import op
import sqlalchemy as sa


revision = "202605030001"
down_revision = "202605020005"
branch_labels = None
depends_on = None


def _schemas() -> tuple[str, str]:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return f"{app_schema}_definitions", f"{app_schema}_runtime"


def upgrade() -> None:
    definitions_schema, runtime_schema = _schemas()

    # 1. UNIQUE (organization_id, entity_type_id) on entity_types so the new
    #    composite FK has a valid target. entity_type_id is already PK
    #    (uniquely identifies a row), so this is a no-op constraint
    #    addition that just lets us reference both columns together.
    op.create_unique_constraint(
        "uq_entity_types_org_id_entity_type_id",
        "entity_types",
        ["organization_id", "entity_type_id"],
        schema=definitions_schema,
    )

    # 2. Drop the existing single-column FK that only checked entity_type_id.
    op.drop_constraint(
        "fk_entities_entity_type_id",
        "entities",
        type_="foreignkey",
        schema=runtime_schema,
    )

    # 3. Add the composite FK that ties (org, type_id) together.
    op.create_foreign_key(
        "fk_entities_org_entity_type_id",
        source_table="entities",
        referent_table="entity_types",
        local_cols=["organization_id", "entity_type_id"],
        remote_cols=["organization_id", "entity_type_id"],
        ondelete="RESTRICT",
        source_schema=runtime_schema,
        referent_schema=definitions_schema,
    )


def downgrade() -> None:
    definitions_schema, runtime_schema = _schemas()

    op.drop_constraint(
        "fk_entities_org_entity_type_id",
        "entities",
        type_="foreignkey",
        schema=runtime_schema,
    )

    op.create_foreign_key(
        "fk_entities_entity_type_id",
        source_table="entities",
        referent_table="entity_types",
        local_cols=["entity_type_id"],
        remote_cols=["entity_type_id"],
        ondelete="RESTRICT",
        source_schema=runtime_schema,
        referent_schema=definitions_schema,
    )

    op.drop_constraint(
        "uq_entity_types_org_id_entity_type_id",
        "entity_types",
        type_="unique",
        schema=definitions_schema,
    )
