"""Add the method library: categories, methods, versions and version fields.

A method's name, description and category are live editable state. Its field list
is versioned, and each listed field pins a Field Library version so the shape a
method was built against cannot change underneath it.

Composite foreign keys carry organization_id throughout, matching the field
library, so no row can join parents from two tenants. The link into
field_library_field_versions deliberately does not cascade, so the database
refuses to hard-delete a field a method version still lists.

Revision ID: 202608210003
Revises: 202608220003
Create Date: 2026-08-21
"""

from __future__ import annotations

import os

import sqlalchemy as sa

from alembic import op

revision = "202608210003"
down_revision = "202608220003"
branch_labels = None
depends_on = None

IDENTIFIER_LENGTH = 36
METHOD_CODE_LENGTH = 128
METHOD_NAME_LENGTH = 256
CATEGORY_NAME_LENGTH = 256
LABEL_LENGTH = 256
PLACEHOLDER_LENGTH = 256


def _definitions_schema() -> str:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return f"{app_schema}_definitions"


def _timestamps() -> list[sa.Column]:
    return [
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
    ]


def _create_categories(schema: str) -> None:
    op.create_table(
        "method_library_categories",
        sa.Column("id", sa.String(IDENTIFIER_LENGTH), nullable=False),
        sa.Column("organization_id", sa.String(IDENTIFIER_LENGTH), nullable=False),
        sa.Column("name", sa.String(CATEGORY_NAME_LENGTH), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_method_library_categories"),
        sa.UniqueConstraint("organization_id", "id", name="uq_method_library_categories_org_id"),
        schema=schema,
    )
    op.create_index(
        "uq_method_library_categories_org_name",
        "method_library_categories",
        ["organization_id", sa.text("lower(name)")],
        unique=True,
        schema=schema,
    )
    op.create_index(
        "ix_method_library_categories_organization_id",
        "method_library_categories",
        ["organization_id"],
        schema=schema,
    )


def _create_methods(schema: str) -> None:
    op.create_table(
        "method_library_methods",
        sa.Column("method_id", sa.String(IDENTIFIER_LENGTH), nullable=False),
        sa.Column("organization_id", sa.String(IDENTIFIER_LENGTH), nullable=False),
        sa.Column("method_code", sa.String(METHOD_CODE_LENGTH), nullable=False),
        sa.Column("name", sa.String(METHOD_NAME_LENGTH), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category_id", sa.String(IDENTIFIER_LENGTH), nullable=True),
        sa.Column("created_by", sa.String(IDENTIFIER_LENGTH), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("method_id", name="pk_method_library_methods"),
        sa.UniqueConstraint(
            "organization_id", "method_id", name="uq_method_library_methods_org_id"
        ),
        sa.ForeignKeyConstraint(
            ["category_id", "organization_id"],
            [
                f"{schema}.method_library_categories.id",
                f"{schema}.method_library_categories.organization_id",
            ],
            name="fk_method_library_methods_category",
        ),
        schema=schema,
    )
    # method_code is the method's permanent identifier: unique per organization,
    # case-insensitively, among live rows only, so archiving frees it for reuse.
    op.create_index(
        "uq_method_library_methods_org_code_active",
        "method_library_methods",
        ["organization_id", sa.text("lower(method_code)")],
        unique=True,
        schema=schema,
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    for column in ("organization_id", "category_id"):
        op.create_index(
            f"ix_method_library_methods_{column}",
            "method_library_methods",
            [column],
            schema=schema,
        )


def _create_versions(schema: str) -> None:
    op.create_table(
        "method_library_method_versions",
        sa.Column("version_id", sa.String(IDENTIFIER_LENGTH), nullable=False),
        sa.Column("method_id", sa.String(IDENTIFIER_LENGTH), nullable=False),
        sa.Column("organization_id", sa.String(IDENTIFIER_LENGTH), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_latest", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.String(IDENTIFIER_LENGTH), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("version_id", name="pk_method_library_method_versions"),
        sa.UniqueConstraint(
            "method_id", "version", name="uq_method_library_versions_method_version"
        ),
        sa.UniqueConstraint(
            "version_id", "organization_id", name="uq_method_library_versions_version_org"
        ),
        sa.ForeignKeyConstraint(
            ["method_id", "organization_id"],
            [
                f"{schema}.method_library_methods.method_id",
                f"{schema}.method_library_methods.organization_id",
            ],
            name="fk_method_library_versions_method",
            ondelete="CASCADE",
        ),
        schema=schema,
    )
    # At most one current version per method, enforced by the database.
    op.create_index(
        "uq_method_library_versions_method_latest",
        "method_library_method_versions",
        ["method_id"],
        unique=True,
        schema=schema,
        postgresql_where=sa.text("is_latest"),
    )
    for column in ("method_id", "organization_id"):
        op.create_index(
            f"ix_method_library_versions_{column}",
            "method_library_method_versions",
            [column],
            schema=schema,
        )


def _create_version_fields(schema: str) -> None:
    op.create_table(
        "method_library_method_version_fields",
        sa.Column("id", sa.String(IDENTIFIER_LENGTH), nullable=False),
        sa.Column("method_version_id", sa.String(IDENTIFIER_LENGTH), nullable=False),
        sa.Column("library_field_id", sa.String(IDENTIFIER_LENGTH), nullable=False),
        sa.Column("field_version_id", sa.String(IDENTIFIER_LENGTH), nullable=False),
        sa.Column("label", sa.String(LABEL_LENGTH), nullable=True),
        sa.Column("placeholder", sa.String(PLACEHOLDER_LENGTH), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("organization_id", sa.String(IDENTIFIER_LENGTH), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_method_library_method_version_fields"),
        sa.UniqueConstraint(
            "method_version_id",
            "library_field_id",
            name="uq_method_library_version_fields_version_field",
        ),
        sa.ForeignKeyConstraint(
            ["method_version_id", "organization_id"],
            [
                f"{schema}.method_library_method_versions.version_id",
                f"{schema}.method_library_method_versions.organization_id",
            ],
            name="fk_method_library_version_fields_version",
            ondelete="CASCADE",
        ),
        # No cascade on either: this is the guard that stops a hard delete of a
        # field, or a field version, that a method version still lists.
        sa.ForeignKeyConstraint(
            ["field_version_id", "library_field_id"],
            [
                f"{schema}.field_library_field_versions.version_id",
                f"{schema}.field_library_field_versions.library_field_id",
            ],
            name="fk_method_library_version_fields_field_version",
        ),
        sa.ForeignKeyConstraint(
            ["field_version_id", "organization_id"],
            [
                f"{schema}.field_library_field_versions.version_id",
                f"{schema}.field_library_field_versions.organization_id",
            ],
            name="fk_method_library_version_fields_field_org",
        ),
        schema=schema,
    )
    for column in ("method_version_id", "library_field_id", "organization_id"):
        op.create_index(
            f"ix_method_library_version_fields_{column}",
            "method_library_method_version_fields",
            [column],
            schema=schema,
        )


def upgrade() -> None:
    schema = _definitions_schema()
    _create_categories(schema)
    _create_methods(schema)
    _create_versions(schema)
    _create_version_fields(schema)


def downgrade() -> None:
    schema = _definitions_schema()
    for table in (
        "method_library_method_version_fields",
        "method_library_method_versions",
        "method_library_methods",
        "method_library_categories",
    ):
        op.drop_table(table, schema=schema)
