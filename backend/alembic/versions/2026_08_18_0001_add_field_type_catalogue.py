"""Add the field-type catalogue and per-organization enablement.

Codes match the form builder's selector; Document and Timer/Duration seed
unavailable. No enablement rows, so existing orgs keep every type.

Revision ID: 202608180001
Revises: 202608140002
Create Date: 2026-08-18
"""

from __future__ import annotations

import os

import sqlalchemy as sa

from alembic import op

revision = "202608180001"
down_revision = "202608140002"
branch_labels = None
depends_on = None

# (code, label, engine_type, config_kind, is_available, sort_order)
_CATALOGUE_SEED: tuple[tuple[str, str, str | None, str, bool, int], ...] = (
    ("text", "Text", "string", "none", True, 10),
    ("textarea", "Text Area", "text", "none", True, 20),
    ("email", "Email", "email", "none", True, 30),
    ("phone", "Phone", "phone", "none", True, 40),
    ("integer", "Integer", "int", "none", True, 50),
    ("datetime", "Date & Time", "datetime", "none", True, 60),
    ("select", "Select", "enum", "enum_values", True, 70),
    ("multi_select", "Multi Select", "multi_select", "enum_values", True, 80),
    ("picklist_multi", "Picklist Multi (Dropdown Add)", "multi_select", "picklist", True, 90),
    ("boolean", "Checkbox", "boolean", "none", True, 100),
    ("url", "URL", "url", "none", True, 110),
    ("currency", "Currency", "currency", "currency", True, 120),
    ("table", "Table / Grid", "json", "table", True, 130),
    ("auto_number", "Auto Number", "auto_number", "auto_number", True, 140),
    ("document", "Document", None, "none", False, 150),
    ("timer_duration", "Timer/Duration", None, "none", False, 160),
)


def _definitions_schema() -> str:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return f"{app_schema}_definitions"


def upgrade() -> None:
    definitions_schema = _definitions_schema()

    op.create_table(
        "field_type_catalogue",
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("engine_type", sa.String(64), nullable=True),
        sa.Column("config_kind", sa.String(64), nullable=False, server_default="none"),
        sa.Column("is_available", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
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
        sa.PrimaryKeyConstraint("code", name="pk_field_type_catalogue"),
        schema=definitions_schema,
    )
    op.create_index(
        "ix_field_type_catalogue_is_available",
        "field_type_catalogue",
        ["is_available"],
        schema=definitions_schema,
    )

    op.create_table(
        "organization_field_types",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("field_type_code", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
        sa.PrimaryKeyConstraint("id", name="pk_organization_field_types"),
        sa.UniqueConstraint(
            "organization_id", "field_type_code", name="uq_organization_field_types_org_code"
        ),
        schema=definitions_schema,
    )
    op.create_index(
        "ix_organization_field_types_organization_id",
        "organization_field_types",
        ["organization_id"],
        schema=definitions_schema,
    )

    insert_entry = sa.text(
        f"""
        INSERT INTO "{definitions_schema}".field_type_catalogue
            (code, label, engine_type, config_kind, is_available, sort_order)
        VALUES (:code, :label, :engine_type, :config_kind, :is_available, :sort_order)
        ON CONFLICT (code) DO NOTHING
        """
    )
    connection = op.get_bind()
    for code, label, engine_type, config_kind, is_available, sort_order in _CATALOGUE_SEED:
        connection.execute(
            insert_entry,
            {
                "code": code,
                "label": label,
                "engine_type": engine_type,
                "config_kind": config_kind,
                "is_available": is_available,
                "sort_order": sort_order,
            },
        )


def downgrade() -> None:
    definitions_schema = _definitions_schema()
    op.drop_index(
        "ix_organization_field_types_organization_id",
        table_name="organization_field_types",
        schema=definitions_schema,
    )
    op.drop_table("organization_field_types", schema=definitions_schema)
    op.drop_index(
        "ix_field_type_catalogue_is_available",
        table_name="field_type_catalogue",
        schema=definitions_schema,
    )
    op.drop_table("field_type_catalogue", schema=definitions_schema)
