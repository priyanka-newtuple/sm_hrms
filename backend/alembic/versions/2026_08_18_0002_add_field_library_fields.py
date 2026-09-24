"""Add the field library: field identities and their versions.

field_key is a field's only permanent member. Name and type live on the identity
as the current values, and every version freezes the name and type it was created
under, so history is never rewritten.

Revision ID: 202608180002
Revises: 202608180001
Create Date: 2026-08-18
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "202608180002"
down_revision = "202608180001"
branch_labels = None
depends_on = None

IDENTIFIER_LENGTH = 36
FIELD_NAME_LENGTH = 256
FIELD_KEY_LENGTH = 128
FIELD_TYPE_CODE_LENGTH = 64


def _definitions_schema() -> str:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return f"{app_schema}_definitions"


def upgrade() -> None:
    definitions_schema = _definitions_schema()

    op.create_table(
        "field_library_fields",
        sa.Column("library_field_id", sa.String(IDENTIFIER_LENGTH), nullable=False),
        sa.Column("field_count_id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("organization_id", sa.String(IDENTIFIER_LENGTH), nullable=False),
        sa.Column("name", sa.String(FIELD_NAME_LENGTH), nullable=False),
        sa.Column("field_key", sa.String(FIELD_KEY_LENGTH), nullable=False),
        sa.Column("field_type", sa.String(FIELD_TYPE_CODE_LENGTH), nullable=False),
        sa.Column("created_by", sa.String(IDENTIFIER_LENGTH), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("library_field_id", name="pk_field_library_fields"),
        sa.UniqueConstraint("field_count_id", name="uq_field_library_fields_count_id"),
        # Redundant alone, but required as the target of tenant-safe composite FKs.
        sa.UniqueConstraint(
            "organization_id", "library_field_id", name="uq_field_library_fields_org_field"
        ),
        schema=definitions_schema,
    )
    # Name is unique per organization per type, so "Volume" can exist as both an
    # integer and a text field, while field_key stays unique on its own. Both
    # comparisons ignore case; the stored casing is untouched.
    op.create_index(
        "uq_field_library_fields_org_name_type_active",
        "field_library_fields",
        ["organization_id", sa.text("lower(name)"), "field_type"],
        unique=True,
        schema=definitions_schema,
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    op.create_index(
        "uq_field_library_fields_org_key_active",
        "field_library_fields",
        ["organization_id", sa.text("lower(field_key)")],
        unique=True,
        schema=definitions_schema,
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    op.create_index(
        "ix_field_library_fields_organization_id",
        "field_library_fields",
        ["organization_id"],
        schema=definitions_schema,
    )

    op.create_table(
        "field_library_field_versions",
        sa.Column("version_id", sa.String(IDENTIFIER_LENGTH), nullable=False),
        sa.Column("library_field_id", sa.String(IDENTIFIER_LENGTH), nullable=False),
        sa.Column("organization_id", sa.String(IDENTIFIER_LENGTH), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        # The identity's name and type at the moment this version was created, both
        # frozen, so later changes leave older versions showing what they were
        # made under. A type change always produces a new version.
        sa.Column("name", sa.String(FIELD_NAME_LENGTH), nullable=False),
        sa.Column("field_type", sa.String(FIELD_TYPE_CODE_LENGTH), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "settings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("is_latest", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.String(IDENTIFIER_LENGTH), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("version_id", name="pk_field_library_field_versions"),
        sa.ForeignKeyConstraint(
            ["library_field_id", "organization_id"],
            [
                f"{definitions_schema}.field_library_fields.library_field_id",
                f"{definitions_schema}.field_library_fields.organization_id",
            ],
            name="fk_field_library_versions_field",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "library_field_id", "version", name="uq_field_library_versions_field_version"
        ),
        # Both redundant alone; each is the target of a composite FK on the
        # connector, one pinning tenant and one pinning version-to-field.
        sa.UniqueConstraint(
            "version_id", "organization_id", name="uq_field_library_versions_version_org"
        ),
        sa.UniqueConstraint(
            "version_id", "library_field_id", name="uq_field_library_versions_version_field"
        ),
        schema=definitions_schema,
    )
    # At most one current version per field, enforced by the database rather than
    # by whoever remembers to clear the previous flag.
    op.create_index(
        "uq_field_library_versions_field_latest",
        "field_library_field_versions",
        ["library_field_id"],
        unique=True,
        schema=definitions_schema,
        postgresql_where=sa.text("is_latest"),
    )
    op.create_index(
        "ix_field_library_versions_library_field_id",
        "field_library_field_versions",
        ["library_field_id"],
        schema=definitions_schema,
    )
    op.create_index(
        "ix_field_library_versions_organization_id",
        "field_library_field_versions",
        ["organization_id"],
        schema=definitions_schema,
    )


def downgrade() -> None:
    definitions_schema = _definitions_schema()
    for index_name in (
        "ix_field_library_versions_organization_id",
        "ix_field_library_versions_library_field_id",
        "uq_field_library_versions_field_latest",
    ):
        op.drop_index(
            index_name, table_name="field_library_field_versions", schema=definitions_schema
        )
    op.drop_table("field_library_field_versions", schema=definitions_schema)

    for index_name in (
        "ix_field_library_fields_organization_id",
        "uq_field_library_fields_org_key_active",
        "uq_field_library_fields_org_name_type_active",
    ):
        op.drop_index(index_name, table_name="field_library_fields", schema=definitions_schema)
    op.drop_table("field_library_fields", schema=definitions_schema)
