"""Add the connector table linking forms to library fields.

Records which field version a form uses, and in what order. Links pin a specific
version, so editing a field later never changes what an existing form shows.
All foreign keys are composite, pinning both tenant and version-to-field.

Revision ID: 202608190001
Revises: 202608180002
Create Date: 2026-08-19
"""

from __future__ import annotations

import os

import sqlalchemy as sa

from alembic import op

revision = "202608190001"
down_revision = "202608180002"
branch_labels = None
depends_on = None

IDENTIFIER_LENGTH = 36


def _definitions_schema() -> str:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return f"{app_schema}_definitions"


def upgrade() -> None:
    definitions_schema = _definitions_schema()

    # Purely additive: `id` is already the primary key, so (organization_id, id)
    # is trivially unique and this cannot fail on existing rows or change any
    # behaviour. It exists solely to be the target of the composite FK below.
    op.create_unique_constraint(
        "uq_entity_type_schema_org_id",
        "entity_type_schema",
        ["organization_id", "id"],
        schema=definitions_schema,
    )

    op.create_table(
        "entity_type_schema_fields",
        sa.Column("id", sa.String(IDENTIFIER_LENGTH), nullable=False),
        sa.Column("schema_id", sa.String(IDENTIFIER_LENGTH), nullable=False),
        sa.Column("version_id", sa.String(IDENTIFIER_LENGTH), nullable=False),
        # Denormalised from the version, like organization_id, so the uniqueness
        # rule and lookups work without a join. Tied to version_id by FK below.
        sa.Column("library_field_id", sa.String(IDENTIFIER_LENGTH), nullable=False),
        sa.Column("organization_id", sa.String(IDENTIFIER_LENGTH), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
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
        sa.PrimaryKeyConstraint("id", name="pk_entity_type_schema_fields"),
        # Composite on organization_id so the database itself refuses a link
        # whose form or field belongs to a different organization. Single-column
        # keys would only prove the parents exist, not that they are same-tenant.
        sa.ForeignKeyConstraint(
            ["schema_id", "organization_id"],
            [
                f"{definitions_schema}.entity_type_schema.id",
                f"{definitions_schema}.entity_type_schema.organization_id",
            ],
            name="fk_entity_type_schema_fields_schema",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["library_field_id", "organization_id"],
            [
                f"{definitions_schema}.field_library_fields.library_field_id",
                f"{definitions_schema}.field_library_fields.organization_id",
            ],
            name="fk_entity_type_schema_fields_library_field",
        ),
        # Pins the link to one version, and ties that version to the field named
        # alongside it, so the two can never drift apart.
        sa.ForeignKeyConstraint(
            ["version_id", "organization_id"],
            [
                f"{definitions_schema}.field_library_field_versions.version_id",
                f"{definitions_schema}.field_library_field_versions.organization_id",
            ],
            name="fk_entity_type_schema_fields_version",
        ),
        sa.ForeignKeyConstraint(
            ["version_id", "library_field_id"],
            [
                f"{definitions_schema}.field_library_field_versions.version_id",
                f"{definitions_schema}.field_library_field_versions.library_field_id",
            ],
            name="fk_entity_type_schema_fields_version_field",
        ),
        sa.UniqueConstraint(
            "schema_id", "library_field_id", name="uq_entity_type_schema_fields_schema_field"
        ),
        schema=definitions_schema,
    )
    op.create_index(
        "ix_entity_type_schema_fields_schema_id",
        "entity_type_schema_fields",
        ["schema_id"],
        schema=definitions_schema,
    )
    op.create_index(
        "ix_entity_type_schema_fields_version_id",
        "entity_type_schema_fields",
        ["version_id"],
        schema=definitions_schema,
    )
    op.create_index(
        "ix_entity_type_schema_fields_library_field_id",
        "entity_type_schema_fields",
        ["library_field_id"],
        schema=definitions_schema,
    )
    op.create_index(
        "ix_entity_type_schema_fields_organization_id",
        "entity_type_schema_fields",
        ["organization_id"],
        schema=definitions_schema,
    )


def downgrade() -> None:
    definitions_schema = _definitions_schema()
    for index_name in (
        "ix_entity_type_schema_fields_organization_id",
        "ix_entity_type_schema_fields_library_field_id",
        "ix_entity_type_schema_fields_version_id",
        "ix_entity_type_schema_fields_schema_id",
    ):
        op.drop_index(
            index_name, table_name="entity_type_schema_fields", schema=definitions_schema
        )
    op.drop_table("entity_type_schema_fields", schema=definitions_schema)
    op.drop_constraint(
        "uq_entity_type_schema_org_id",
        "entity_type_schema",
        schema=definitions_schema,
        type_="unique",
    )
