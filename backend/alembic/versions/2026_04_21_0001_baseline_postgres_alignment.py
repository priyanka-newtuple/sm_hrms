"""Baseline postgres alignment for modular backend models.

Revision ID: 202604210001
Revises:
Create Date: 2026-04-21 00:01:00
"""

from __future__ import annotations

import os

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "202604210001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create baseline tables for auth, org, user, roles, workflow, mail, llm, projections."""
    schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    op.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))

    # organizations (without requested_by FK first to avoid cycle with users)
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("logo_url", sa.String(length=512), nullable=True),
        sa.Column("requested_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizations")),
        schema=schema,
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True, schema=schema)
    op.create_index("ix_organizations_domain", "organizations", ["domain"], unique=True, schema=schema)
    op.create_index("ix_organizations_status", "organizations", ["status"], unique=False, schema=schema)
    op.create_index("ix_organizations_requested_by_user_id", "organizations", ["requested_by_user_id"], unique=False, schema=schema)

    # users
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("avatar_url", sa.String(length=2048), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("auth_type", sa.String(length=16), nullable=False),
        sa.Column("google_id", sa.String(length=255), nullable=True),
        sa.Column("microsoft_id", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], [f"{schema}.organizations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        schema=schema,
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True, schema=schema)
    op.create_index("ix_users_google_id", "users", ["google_id"], unique=True, schema=schema)
    op.create_index("ix_users_microsoft_id", "users", ["microsoft_id"], unique=True, schema=schema)
    op.create_index("ix_users_organization_id", "users", ["organization_id"], unique=False, schema=schema)
    op.create_index("ix_users_auth_type", "users", ["auth_type"], unique=False, schema=schema)

    # add deferred organizations.requested_by_user_id -> users.id FK
    op.create_foreign_key(
        "fk_organizations_requested_by_user_id_users",
        source_table="organizations",
        referent_table="users",
        local_cols=["requested_by_user_id"],
        remote_cols=["id"],
        source_schema=schema,
        referent_schema=schema,
        ondelete="SET NULL",
    )

    # user_organizations
    op.create_table(
        "user_organizations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], [f"{schema}.organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], [f"{schema}.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_organizations")),
        sa.UniqueConstraint("user_id", "organization_id", name="uq_user_organization"),
        schema=schema,
    )
    op.create_index("ix_user_organizations_user_id", "user_organizations", ["user_id"], unique=False, schema=schema)
    op.create_index("ix_user_organizations_organization_id", "user_organizations", ["organization_id"], unique=False, schema=schema)
    op.create_index("ix_user_organizations_user_org", "user_organizations", ["user_id", "organization_id"], unique=False, schema=schema)

    # refresh_tokens
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], [f"{schema}.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
        schema=schema,
    )
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=False, schema=schema)
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"], unique=False, schema=schema)

    # invitations
    op.create_table(
        "invitations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("invited_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["accepted_user_id"], [f"{schema}.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["invited_by_user_id"], [f"{schema}.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], [f"{schema}.organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invitations")),
        schema=schema,
    )
    op.create_index("ix_invitations_organization_id", "invitations", ["organization_id"], unique=False, schema=schema)
    op.create_index("ix_invitations_email", "invitations", ["email"], unique=False, schema=schema)
    op.create_index("ix_invitations_token", "invitations", ["token"], unique=True, schema=schema)
    op.create_index(
        "ix_invitations_org_email_pending",
        "invitations",
        ["organization_id", "email"],
        unique=False,
        schema=schema,
        postgresql_where=sa.text("status = 'pending'"),
    )

    # roles
    op.create_table(
        "roles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("color", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], [f"{schema}.organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_roles")),
        sa.UniqueConstraint("organization_id", "name", name="uq_roles_org_name"),
        schema=schema,
    )
    op.create_index("ix_roles_organization_id", "roles", ["organization_id"], unique=False, schema=schema)

    # role_permissions
    op.create_table(
        "role_permissions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("role_id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("allowed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], [f"{schema}.roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_role_permissions")),
        sa.UniqueConstraint("role_id", "entity_type", "action", name="uq_role_permissions_unique"),
        schema=schema,
    )
    op.create_index("ix_role_permissions_role_id", "role_permissions", ["role_id"], unique=False, schema=schema)

    # field_permissions
    op.create_table(
        "field_permissions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("role_id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=128), nullable=False),
        sa.Column("field_name", sa.String(length=128), nullable=False),
        sa.Column("can_view", sa.Boolean(), nullable=False),
        sa.Column("can_edit", sa.Boolean(), nullable=False),
        sa.Column("mask_value", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], [f"{schema}.roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_field_permissions")),
        sa.UniqueConstraint("role_id", "entity_type", "field_name", name="uq_field_permissions_unique"),
        schema=schema,
    )
    op.create_index("ix_field_permissions_role_id", "field_permissions", ["role_id"], unique=False, schema=schema)

    # user_roles
    op.create_table(
        "user_roles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("role_id", sa.String(length=36), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("assigned_by", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], [f"{schema}.organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], [f"{schema}.roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], [f"{schema}.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_roles")),
        sa.UniqueConstraint("user_id", "organization_id", "role_id", name="uq_user_roles_unique"),
        schema=schema,
    )
    op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"], unique=False, schema=schema)
    op.create_index("ix_user_roles_organization_id", "user_roles", ["organization_id"], unique=False, schema=schema)
    op.create_index("ix_user_roles_role_id", "user_roles", ["role_id"], unique=False, schema=schema)
    op.create_index("ix_user_roles_user_org", "user_roles", ["user_id", "organization_id"], unique=False, schema=schema)

    # mail.email_configs
    op.create_table(
        "email_configs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("encrypted_access_key_id", sa.Text(), nullable=False),
        sa.Column("encrypted_secret_key", sa.Text(), nullable=False),
        sa.Column("access_key_hint", sa.String(length=32), nullable=True),
        sa.Column("region", sa.String(length=32), nullable=True),
        sa.Column("smtp_host", sa.String(length=256), nullable=True),
        sa.Column("smtp_port", sa.Integer(), nullable=True),
        sa.Column("smtp_use_tls", sa.Boolean(), nullable=True),
        sa.Column("from_email", sa.String(length=256), nullable=False),
        sa.Column("from_name", sa.String(length=128), nullable=True),
        sa.Column("reply_to_email", sa.String(length=256), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("validation_status", sa.String(length=16), nullable=True),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], [f"{schema}.organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_configs")),
        schema=schema,
    )
    op.create_index("ix_email_configs_organization_id", "email_configs", ["organization_id"], unique=False, schema=schema)
    op.create_index("ix_email_configs_org_provider", "email_configs", ["organization_id", "provider"], unique=True, schema=schema)

    # mail.inbound_emails
    op.create_table(
        "inbound_emails",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("message_id", sa.String(length=128), nullable=True),
        sa.Column("s3_bucket", sa.String(length=255), nullable=True),
        sa.Column("s3_key", sa.String(length=1024), nullable=True),
        sa.Column("sender_email", sa.String(length=255), nullable=True),
        sa.Column("sender_name", sa.String(length=255), nullable=True),
        sa.Column("recipient_emails", sa.JSON(), nullable=True),
        sa.Column("subject", sa.String(length=512), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("candidate_id", sa.String(length=36), nullable=True),
        sa.Column("application_id", sa.String(length=36), nullable=True),
        sa.Column("attachments", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], [f"{schema}.organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inbound_emails")),
        schema=schema,
    )
    op.create_index("ix_inbound_emails_organization_id", "inbound_emails", ["organization_id"], unique=False, schema=schema)
    op.create_index("ix_inbound_emails_status", "inbound_emails", ["status"], unique=False, schema=schema)
    op.create_index("ix_inbound_emails_message_id", "inbound_emails", ["message_id"], unique=True, schema=schema)
    op.create_index("ix_inbound_emails_org_status", "inbound_emails", ["organization_id", "status"], unique=False, schema=schema)

    # llm_api_keys
    op.create_table(
        "llm_api_keys",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("encrypted_key", sa.Text(), nullable=False),
        sa.Column("display_hint", sa.String(length=32), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("validation_status", sa.String(length=16), nullable=True),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], [f"{schema}.organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_api_keys")),
        schema=schema,
    )
    op.create_index("ix_llm_api_keys_organization_id", "llm_api_keys", ["organization_id"], unique=False, schema=schema)
    op.create_index("ix_llm_api_keys_org_provider", "llm_api_keys", ["organization_id", "provider"], unique=True, schema=schema)

    # projections.view_definitions
    op.create_table(
        "view_definitions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_entity_type", sa.String(length=64), nullable=False),
        sa.Column("primary_key_field", sa.String(length=64), nullable=True),
        sa.Column("source_fields", sa.JSON(), nullable=True),
        sa.Column("denormalized_fields", sa.JSON(), nullable=True),
        sa.Column("include_state", sa.Boolean(), nullable=True),
        sa.Column("group_by_field", sa.String(length=64), nullable=True),
        sa.Column("available_filters", sa.JSON(), nullable=True),
        sa.Column("sla_config", sa.JSON(), nullable=True),
        sa.Column("aggregations", sa.JSON(), nullable=True),
        sa.Column("default_sort", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], [f"{schema}.organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_view_definitions")),
        schema=schema,
    )
    op.create_index("ix_view_definitions_organization_id", "view_definitions", ["organization_id"], unique=False, schema=schema)

    # projections.projection_rows
    op.create_table(
        "projection_rows",
        sa.Column("view_name", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("current_state", sa.String(length=128), nullable=True),
        sa.Column("state_entered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("machine_name", sa.String(length=128), nullable=True),
        sa.Column("machine_version", sa.Integer(), nullable=True),
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sla_risk", sa.String(length=32), nullable=True),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], [f"{schema}.organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("view_name", "entity_id", name=op.f("pk_projection_rows")),
        schema=schema,
    )
    op.create_index("ix_projection_rows_organization_id", "projection_rows", ["organization_id"], unique=False, schema=schema)
    op.create_index("ix_projection_rows_entity_type", "projection_rows", ["entity_type"], unique=False, schema=schema)
    op.create_index("ix_projection_rows_current_state", "projection_rows", ["current_state"], unique=False, schema=schema)
    op.create_index("ix_projection_rows_machine_name", "projection_rows", ["machine_name"], unique=False, schema=schema)
    op.create_index("ix_projection_rows_sla_due_at", "projection_rows", ["sla_due_at"], unique=False, schema=schema)
    op.create_index("ix_projection_rows_sla_risk", "projection_rows", ["sla_risk"], unique=False, schema=schema)

    # workflow_state_machines
    op.create_table(
        "workflow_state_machines",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("machine_key", sa.String(length=128), nullable=False),
        sa.Column("machine_name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("entity_type", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("definition_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_state_machines")),
        sa.UniqueConstraint("organization_id", "machine_name", "version", name="uq_workflow_machine_version"),
        schema=schema,
    )
    op.create_index("ix_workflow_state_machines_organization_id", "workflow_state_machines", ["organization_id"], unique=False, schema=schema)
    op.create_index("ix_workflow_state_machines_machine_key", "workflow_state_machines", ["machine_key"], unique=False, schema=schema)
    op.create_index("ix_workflow_state_machines_machine_name", "workflow_state_machines", ["machine_name"], unique=False, schema=schema)
    op.create_index("ix_workflow_state_machines_entity_type", "workflow_state_machines", ["entity_type"], unique=False, schema=schema)
    op.create_index(
        "ix_workflow_machine_active",
        "workflow_state_machines",
        ["organization_id", "machine_name", "is_active"],
        unique=False,
        schema=schema,
    )

    # workflow_entity_schema_picklists
    op.create_table(
        "workflow_entity_schema_picklists",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("schema_key", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("entity_type", sa.String(length=128), nullable=False),
        sa.Column("fields_json", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_entity_schema_picklists")),
        sa.UniqueConstraint("organization_id", "schema_key", name="uq_workflow_schema_picklist"),
        schema=schema,
    )
    op.create_index("ix_workflow_entity_schema_picklists_organization_id", "workflow_entity_schema_picklists", ["organization_id"], unique=False, schema=schema)
    op.create_index("ix_workflow_entity_schema_picklists_schema_key", "workflow_entity_schema_picklists", ["schema_key"], unique=False, schema=schema)
    op.create_index("ix_workflow_entity_schema_picklists_entity_type", "workflow_entity_schema_picklists", ["entity_type"], unique=False, schema=schema)
    op.create_index("ix_workflow_entity_schema_picklists_content_hash", "workflow_entity_schema_picklists", ["content_hash"], unique=False, schema=schema)
    op.create_index(
        "ix_workflow_schema_picklist_lookup",
        "workflow_entity_schema_picklists",
        ["organization_id", "schema_key", "is_active"],
        unique=False,
        schema=schema,
    )

    # workflow_definition_reports
    op.create_table(
        "workflow_definition_reports",
        sa.Column("report_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("report_type", sa.String(length=32), nullable=False),
        sa.Column("machine_name", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=True),
        sa.Column("base_version", sa.Integer(), nullable=True),
        sa.Column("candidate_version", sa.Integer(), nullable=True),
        sa.Column("valid", sa.Boolean(), nullable=True),
        sa.Column("checked_entities", sa.Integer(), nullable=True),
        sa.Column("compatible_entities", sa.Integer(), nullable=True),
        sa.Column("incompatible_entities", sa.Integer(), nullable=True),
        sa.Column("issues_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("report_id", name=op.f("pk_workflow_definition_reports")),
        schema=schema,
    )
    op.create_index("ix_workflow_definition_reports_organization_id", "workflow_definition_reports", ["organization_id"], unique=False, schema=schema)
    op.create_index("ix_workflow_definition_reports_report_type", "workflow_definition_reports", ["report_type"], unique=False, schema=schema)
    op.create_index("ix_workflow_definition_reports_machine_name", "workflow_definition_reports", ["machine_name"], unique=False, schema=schema)

    # workflow_entity_states
    op.create_table(
        "workflow_entity_states",
        sa.Column("entity_id", sa.String(length=128), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=128), nullable=False),
        sa.Column("machine_name", sa.String(length=128), nullable=False),
        sa.Column("machine_version", sa.Integer(), nullable=False),
        sa.Column("current_state", sa.String(length=128), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("data_json", sa.Text(), nullable=False),
        sa.Column("state_entered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_transition_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("entity_id", name=op.f("pk_workflow_entity_states")),
        schema=schema,
    )
    op.create_index("ix_workflow_entity_states_organization_id", "workflow_entity_states", ["organization_id"], unique=False, schema=schema)
    op.create_index("ix_workflow_entity_states_machine_name", "workflow_entity_states", ["machine_name"], unique=False, schema=schema)

    # workflow_activity_log
    op.create_table(
        "workflow_activity_log",
        sa.Column("activity_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("activity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=False),
        sa.Column("machine_name", sa.String(length=128), nullable=False),
        sa.Column("machine_version", sa.Integer(), nullable=False),
        sa.Column("trigger", sa.String(length=128), nullable=True),
        sa.Column("from_state", sa.String(length=128), nullable=True),
        sa.Column("to_state", sa.String(length=128), nullable=True),
        sa.Column("actor_id", sa.String(length=128), nullable=True),
        sa.Column("actor_role", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("idempotency_key", sa.String(length=256), nullable=True),
        sa.Column("blocked_reasons_json", sa.Text(), nullable=False),
        sa.Column("executed_tasks_json", sa.Text(), nullable=False),
        sa.Column("committed_response_json", sa.Text(), nullable=True),
        sa.Column("state_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("activity_id", name=op.f("pk_workflow_activity_log")),
        schema=schema,
    )
    op.create_index("ix_workflow_activity_log_organization_id", "workflow_activity_log", ["organization_id"], unique=False, schema=schema)
    op.create_index("ix_workflow_activity_log_activity_type", "workflow_activity_log", ["activity_type"], unique=False, schema=schema)
    op.create_index("ix_workflow_activity_log_entity_id", "workflow_activity_log", ["entity_id"], unique=False, schema=schema)
    op.create_index("ix_workflow_activity_log_idempotency_key", "workflow_activity_log", ["idempotency_key"], unique=False, schema=schema)


def downgrade() -> None:
    """Drop baseline tables in reverse dependency order."""
    schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")

    op.drop_table("workflow_activity_log", schema=schema)
    op.drop_table("workflow_entity_states", schema=schema)
    op.drop_table("workflow_definition_reports", schema=schema)
    op.drop_table("workflow_entity_schema_picklists", schema=schema)
    op.drop_table("workflow_state_machines", schema=schema)
    op.drop_table("projection_rows", schema=schema)
    op.drop_table("view_definitions", schema=schema)
    op.drop_table("llm_api_keys", schema=schema)
    op.drop_table("inbound_emails", schema=schema)
    op.drop_table("email_configs", schema=schema)
    op.drop_table("user_roles", schema=schema)
    op.drop_table("field_permissions", schema=schema)
    op.drop_table("role_permissions", schema=schema)
    op.drop_table("roles", schema=schema)
    op.drop_table("invitations", schema=schema)
    op.drop_table("refresh_tokens", schema=schema)
    op.drop_table("user_organizations", schema=schema)
    op.drop_table("users", schema=schema)
    op.drop_table("organizations", schema=schema)
