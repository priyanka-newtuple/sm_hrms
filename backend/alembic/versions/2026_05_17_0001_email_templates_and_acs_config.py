"""Add email_templates table and ACS fields to email_configs.

Revision ID: 202605170001
Revises: 202605140001
Create Date: 2026-05-17
"""

from __future__ import annotations

import os
import uuid

import sqlalchemy as sa

from alembic import op

revision = "202605170001"
down_revision = "202605140001"
branch_labels = None
depends_on = None


def _app_schema() -> str:
    return os.environ.get("POSTGRES_APP_SCHEMA", "public")


def _definitions_schema() -> str:
    return _app_schema() + "_definitions"


def upgrade() -> None:
    app_schema = _app_schema()
    definitions_schema = _definitions_schema()

    # -- email_templates table --
    op.create_table(
        "email_templates",
        sa.Column("template_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=False),
        sa.Column("form_id", sa.String(36), nullable=True),
        sa.Column("entity_type", sa.String(128), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("template_id", name="pk_email_templates"),
        schema=definitions_schema,
    )
    op.create_index(
        "ix_email_templates_org", "email_templates", ["organization_id"], schema=definitions_schema
    )

    op.execute(
        sa.text(f"""
            INSERT INTO "{definitions_schema}".email_templates
                (template_id, organization_id, name, subject, body_html, form_id, is_system)
            VALUES
                (
                    '{uuid.uuid4()}',
                    NULL,
                    'Default Form Request',
                    'Action Required: Please fill out the form',
                    '<p>Hello,</p><p>You have been requested to fill out a form. Please click the link below to proceed:</p><p><a href="{{{{form_link}}}}">Open Form</a></p><p>This link will expire in 72 hours.</p><p>Thank you.</p>',
                    NULL,
                    true
                )
            ON CONFLICT DO NOTHING;
        """)
    )

    # -- ACS fields on email_configs --
    op.add_column(
        "email_configs",
        sa.Column("acs_endpoint", sa.String(256), nullable=True),
        schema=app_schema,
    )
    op.add_column(
        "email_configs",
        sa.Column("encrypted_connection_string", sa.Text(), nullable=True),
        schema=app_schema,
    )
    op.add_column(
        "email_configs",
        sa.Column("connection_string_hint", sa.String(32), nullable=True),
        schema=app_schema,
    )


def downgrade() -> None:
    app_schema = _app_schema()
    definitions_schema = _definitions_schema()

    op.drop_column("email_configs", "connection_string_hint", schema=app_schema)
    op.drop_column("email_configs", "encrypted_connection_string", schema=app_schema)
    op.drop_column("email_configs", "acs_endpoint", schema=app_schema)
    op.drop_index("ix_email_templates_org", table_name="email_templates", schema=definitions_schema)
    op.drop_table("email_templates", schema=definitions_schema)
