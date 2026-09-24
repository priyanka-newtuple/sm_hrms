"""Add missing tables: agent, entities, filehandler, fileprocessor, integrations, tasks, tools.

Revision ID: 202604270002
Revises: 202604210001
Create Date: 2026-04-27 00:02:00
"""

from __future__ import annotations

import os

from alembic import op
import sqlalchemy as sa

revision = "202604270002"
down_revision = "202604210001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")

    # ── agent_definitions ────────────────────────────────────────────────────
    op.create_table(
        "agent_definitions",
        sa.Column("definition_id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("description", sa.String(512), nullable=True),
        sa.Column("system_prompt", sa.Text, nullable=False),
        sa.Column("allowed_tools", sa.JSON, nullable=True),
        sa.Column("constraints", sa.JSON, nullable=False),
        sa.Column("suggestions", sa.JSON, nullable=False),
        sa.Column("model_override", sa.String(128), nullable=True),
        sa.Column("is_active", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_system", sa.Integer, nullable=False, server_default="0"),
        sa.Column("organization_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("definition_id"),
        schema=schema,
    )
    op.create_index("ix_agent_definitions_organization_id", "agent_definitions", ["organization_id"], schema=schema)
    op.create_index("ix_agent_definitions_org_name", "agent_definitions", ["organization_id", "name"], unique=True, schema=schema)

    # ── agent_sessions ───────────────────────────────────────────────────────
    op.create_table(
        "agent_sessions",
        sa.Column("session_id", sa.String(36), primary_key=True),
        sa.Column("definition_id", sa.String(36), sa.ForeignKey(f"{schema}.agent_definitions.definition_id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("context", sa.JSON, nullable=True),
        sa.Column("title", sa.String(256), nullable=True),
        sa.Column("total_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("message_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("session_id"),
        schema=schema,
    )
    op.create_index("ix_agent_sessions_definition_id", "agent_sessions", ["definition_id"], schema=schema)
    op.create_index("ix_agent_sessions_user_id", "agent_sessions", ["user_id"], schema=schema)
    op.create_index("ix_agent_sessions_organization_id", "agent_sessions", ["organization_id"], schema=schema)
    op.create_index("ix_agent_sessions_user_updated", "agent_sessions", ["user_id", "updated_at"], schema=schema)

    # ── agent_messages ───────────────────────────────────────────────────────
    op.create_table(
        "agent_messages",
        sa.Column("message_id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey(f"{schema}.agent_sessions.session_id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("tool_calls", sa.JSON, nullable=True),
        sa.Column("pending_actions", sa.JSON, nullable=True),
        sa.Column("tokens_used", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("message_id"),
        schema=schema,
    )
    op.create_index("ix_agent_messages_session_id", "agent_messages", ["session_id"], schema=schema)
    op.create_index("ix_agent_messages_session_created", "agent_messages", ["session_id", "created_at"], schema=schema)

    # ── agent_trace_runs ─────────────────────────────────────────────────────
    op.create_table(
        "agent_trace_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("agent_name", sa.String(128), nullable=False),
        sa.Column("run_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("input_message", sa.Text, nullable=True),
        sa.Column("session_id", sa.String(36), nullable=True),
        sa.Column("message_id", sa.String(36), nullable=True),
        sa.Column("context", sa.JSON, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("tokens_used", sa.Integer, nullable=False, server_default="0"),
        sa.Column("iterations", sa.Integer, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema=schema,
    )
    op.create_index("ix_agent_trace_runs_organization_id", "agent_trace_runs", ["organization_id"], schema=schema)
    op.create_index("ix_agent_trace_runs_user_id", "agent_trace_runs", ["user_id"], schema=schema)
    op.create_index("ix_agent_trace_runs_agent_name", "agent_trace_runs", ["agent_name"], schema=schema)
    op.create_index("ix_agent_trace_runs_session_id", "agent_trace_runs", ["session_id"], schema=schema)
    op.create_index("ix_agent_trace_runs_message_id", "agent_trace_runs", ["message_id"], schema=schema)
    op.create_index("ix_agent_trace_runs_expires_at", "agent_trace_runs", ["expires_at"], schema=schema)
    op.create_index("ix_agent_trace_runs_org_started", "agent_trace_runs", ["organization_id", "started_at"], schema=schema)
    op.create_index("ix_agent_trace_runs_org_status", "agent_trace_runs", ["organization_id", "status"], schema=schema)

    # ── agent_trace_events ───────────────────────────────────────────────────
    op.create_table(
        "agent_trace_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey(f"{schema}.agent_trace_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema=schema,
    )
    op.create_index("ix_agent_trace_events_run_id", "agent_trace_events", ["run_id"], schema=schema)
    op.create_index("ix_agent_trace_events_kind", "agent_trace_events", ["kind"], schema=schema)
    op.create_index("ix_agent_trace_events_run_seq", "agent_trace_events", ["run_id", "seq"], schema=schema)

    # ── entities ─────────────────────────────────────────────────────────────
    op.create_table(
        "entities",
        sa.Column("entity_id", sa.String(36), primary_key=True),
        sa.Column("entity_type", sa.String(128), nullable=False),
        sa.Column("schema_name", sa.String(128), nullable=False),
        sa.Column("schema_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("data", sa.JSON, nullable=False),
        sa.Column("owner_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey(f"{schema}.organizations.id", ondelete="CASCADE"), nullable=True),
        sa.PrimaryKeyConstraint("entity_id"),
        schema=schema,
    )
    op.create_index("ix_entities_entity_type", "entities", ["entity_type"], schema=schema)
    op.create_index("ix_entities_organization_id", "entities", ["organization_id"], schema=schema)

    # ── entity_relations ─────────────────────────────────────────────────────
    op.create_table(
        "entity_relations",
        sa.Column("relation_id", sa.String(36), primary_key=True),
        sa.Column("from_entity_id", sa.String(36), nullable=False),
        sa.Column("from_entity_type", sa.String(128), nullable=False),
        sa.Column("to_entity_id", sa.String(36), nullable=False),
        sa.Column("to_entity_type", sa.String(128), nullable=False),
        sa.Column("relation_type", sa.String(128), nullable=False),
        sa.Column("metadata", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey(f"{schema}.organizations.id", ondelete="CASCADE"), nullable=True),
        sa.PrimaryKeyConstraint("relation_id"),
        schema=schema,
    )
    op.create_index("ix_entity_relations_organization_id", "entity_relations", ["organization_id"], schema=schema)
    op.create_index("ix_entity_relations_from", "entity_relations", ["from_entity_type", "from_entity_id"], schema=schema)
    op.create_index("ix_entity_relations_to", "entity_relations", ["to_entity_type", "to_entity_id"], schema=schema)

    # ── entity_state ─────────────────────────────────────────────────────────
    op.create_table(
        "entity_state",
        sa.Column("entity_id", sa.String(36), primary_key=True),
        sa.Column("entity_type", sa.String(128), nullable=False),
        sa.Column("machine_name", sa.String(128), nullable=False),
        sa.Column("machine_version", sa.Integer, nullable=False),
        sa.Column("state", sa.String(128), nullable=False),
        sa.Column("state_entered_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("state_version", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("risk", sa.String(64), nullable=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey(f"{schema}.organizations.id", ondelete="CASCADE"), nullable=False),
        sa.PrimaryKeyConstraint("entity_id"),
        schema=schema,
    )
    op.create_index("ix_entity_state_organization_id", "entity_state", ["organization_id"], schema=schema)

    # ── entity_events ────────────────────────────────────────────────────────
    op.create_table(
        "entity_events",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("entity_type", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("actor_type", sa.String(32), nullable=False),
        sa.Column("actor_id", sa.String(128), nullable=False),
        sa.Column("correlation_id", sa.String(36), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("payload", sa.JSON, nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey(f"{schema}.organizations.id", ondelete="CASCADE"), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
        schema=schema,
    )
    op.create_index("ix_entity_events_entity_id", "entity_events", ["entity_id"], schema=schema)
    op.create_index("ix_entity_events_idempotency_key", "entity_events", ["idempotency_key"], schema=schema)
    op.create_index("ix_entity_events_organization_id", "entity_events", ["organization_id"], schema=schema)

    # ── file_types ───────────────────────────────────────────────────────────
    op.create_table(
        "file_types",
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("type_id", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("folder", sa.String(255), nullable=False),
        sa.Column("allowed_extensions", sa.JSON, nullable=False),
        sa.Column("max_size_mb", sa.Integer, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_system", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("metadata", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("organization_id", "type_id"),
        schema=schema,
    )
    op.create_index("ix_file_types_org_active", "file_types", ["organization_id", "is_active"], schema=schema)

    # ── files ────────────────────────────────────────────────────────────────
    op.create_table(
        "files",
        sa.Column("file_id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("type_id", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("storage_key", sa.String(1024), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("uploaded_by", sa.String(36), nullable=True),
        sa.Column("owner_entity_id", sa.String(36), nullable=True),
        sa.Column("owner_entity_type", sa.String(128), nullable=True),
        sa.Column("metadata", sa.JSON, nullable=False),
        sa.Column("failure_reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("file_id"),
        schema=schema,
    )
    op.create_index("ix_files_organization_id", "files", ["organization_id"], schema=schema)
    op.create_index("ix_files_type_id", "files", ["type_id"], schema=schema)
    op.create_index("ix_files_status", "files", ["status"], schema=schema)
    op.create_index("ux_files_org_storage_key", "files", ["organization_id", "storage_key"], unique=True, schema=schema)
    op.create_index("ix_files_org_type_status", "files", ["organization_id", "type_id", "status"], schema=schema)
    op.create_index("ix_files_org_created", "files", ["organization_id", "created_at"], schema=schema)

    # ── fileprocessor_jobs ───────────────────────────────────────────────────
    op.create_table(
        "fileprocessor_jobs",
        sa.Column("job_id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("file_id", sa.String(36), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("current_stage", sa.String(64), nullable=True),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer, nullable=False, server_default="3"),
        sa.Column("priority", sa.Integer, nullable=False, server_default="5"),
        sa.Column("requested_by", sa.String(36), nullable=True),
        sa.Column("target_schema", sa.JSON, nullable=True),
        sa.Column("llm_policy", sa.JSON, nullable=False),
        sa.Column("agent_policy", sa.JSON, nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("error_code", sa.String(128), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("filename", sa.String(512), nullable=True),
        sa.Column("content_type", sa.String(255), nullable=True),
        sa.Column("storage_key", sa.String(1024), nullable=True),
        sa.Column("execution_mode", sa.String(16), nullable=True),
        sa.Column("agent_name", sa.String(128), nullable=True),
        sa.Column("agent_definition_id", sa.String(36), nullable=True),
        sa.Column("detected_format", sa.String(32), nullable=True),
        sa.Column("success", sa.Boolean, nullable=True),
        sa.Column("classification", sa.JSON, nullable=True),
        sa.Column("structured_output", sa.JSON, nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("confidence_score", sa.Float, nullable=True),
        sa.Column("warnings", sa.JSON, nullable=False),
        sa.Column("errors", sa.JSON, nullable=False),
        sa.Column("provider_trace", sa.JSON, nullable=False),
        sa.Column("stage_log", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("job_id"),
        schema=schema,
    )
    op.create_index("ix_fileprocessor_jobs_organization_id", "fileprocessor_jobs", ["organization_id"], schema=schema)
    op.create_index("ix_fileprocessor_jobs_file_id", "fileprocessor_jobs", ["file_id"], schema=schema)
    op.create_index("ix_fileprocessor_jobs_status", "fileprocessor_jobs", ["status"], schema=schema)
    op.create_index("ix_fileprocessor_jobs_org_status_created", "fileprocessor_jobs", ["organization_id", "status", "created_at"], schema=schema)
    op.create_index("ix_fileprocessor_jobs_org_file_created", "fileprocessor_jobs", ["organization_id", "file_id", "created_at"], schema=schema)
    op.create_index("ux_fileprocessor_jobs_org_idempotency", "fileprocessor_jobs", ["organization_id", "idempotency_key"], unique=True, schema=schema)

    # ── organization_integrations ────────────────────────────────────────────
    op.create_table(
        "organization_integrations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("auth_type", sa.String(32), nullable=False),
        sa.Column("capabilities", sa.JSON, nullable=False),
        sa.Column("display_name", sa.String(128), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="configured"),
        sa.Column("config", sa.JSON, nullable=False),
        sa.Column("encrypted_secret_config", sa.Text, nullable=True),
        sa.Column("secret_hints", sa.JSON, nullable=False),
        sa.Column("validation_status", sa.String(16), nullable=True),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema=schema,
    )
    op.create_index("ix_organization_integrations_organization_id", "organization_integrations", ["organization_id"], schema=schema)
    op.create_index("ix_organization_integrations_provider", "organization_integrations", ["provider"], schema=schema)
    op.create_index("ix_org_integrations_org_provider", "organization_integrations", ["organization_id", "provider"], unique=True, schema=schema)

    # ── integration_capability_defaults ─────────────────────────────────────
    op.create_table(
        "integration_capability_defaults",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("capability", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema=schema,
    )
    op.create_index("ix_integration_capability_defaults_organization_id", "integration_capability_defaults", ["organization_id"], schema=schema)
    op.create_index("ix_integration_capability_defaults_capability", "integration_capability_defaults", ["capability"], schema=schema)
    op.create_index("ix_integration_capability_defaults_org_capability", "integration_capability_defaults", ["organization_id", "capability"], unique=True, schema=schema)

    # ── tasks ────────────────────────────────────────────────────────────────
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("entity_type", sa.String(128), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("assigned_to", sa.String(36), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("priority", sa.String(32), nullable=False, server_default="MEDIUM"),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stage", sa.String(64), nullable=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema=schema,
    )
    op.create_index("ix_tasks_organization_id", "tasks", ["organization_id"], schema=schema)
    op.create_index("ix_tasks_entity_id", "tasks", ["entity_id"], schema=schema)
    op.create_index("ix_tasks_assigned_to", "tasks", ["assigned_to"], schema=schema)
    op.create_index("ix_tasks_entity_stage", "tasks", ["entity_id", "stage"], schema=schema)
    op.create_index("ix_tasks_assigned_status", "tasks", ["assigned_to", "status"], schema=schema)
    op.create_index("ix_tasks_org_entity", "tasks", ["organization_id", "entity_id"], schema=schema)
    op.create_index("ix_tasks_due_date", "tasks", ["due_date"], schema=schema)

    # ── tool_execution_logs ──────────────────────────────────────────────────
    op.create_table(
        "tool_execution_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("actor_id", sa.String(36), nullable=True),
        sa.Column("actor_type", sa.String(32), nullable=True),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column("arguments", sa.JSON, nullable=False),
        sa.Column("result", sa.JSON, nullable=False),
        sa.Column("success", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("execution_backend", sa.String(32), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=True),
        sa.Column("session_id", sa.String(36), nullable=True),
        sa.Column("entity_id", sa.String(36), nullable=True),
        sa.Column("entity_type", sa.String(128), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("metadata", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema=schema,
    )
    op.create_index("ix_tool_execution_logs_organization_id", "tool_execution_logs", ["organization_id"], schema=schema)
    op.create_index("ix_tool_execution_logs_user_id", "tool_execution_logs", ["user_id"], schema=schema)
    op.create_index("ix_tool_execution_logs_actor_id", "tool_execution_logs", ["actor_id"], schema=schema)
    op.create_index("ix_tool_execution_logs_source", "tool_execution_logs", ["source"], schema=schema)
    op.create_index("ix_tool_execution_logs_tool_name", "tool_execution_logs", ["tool_name"], schema=schema)
    op.create_index("ix_tool_execution_logs_success", "tool_execution_logs", ["success"], schema=schema)
    op.create_index("ix_tool_execution_logs_execution_backend", "tool_execution_logs", ["execution_backend"], schema=schema)
    op.create_index("ix_tool_execution_logs_run_id", "tool_execution_logs", ["run_id"], schema=schema)
    op.create_index("ix_tool_execution_logs_session_id", "tool_execution_logs", ["session_id"], schema=schema)
    op.create_index("ix_tool_execution_logs_entity_id", "tool_execution_logs", ["entity_id"], schema=schema)
    op.create_index("ix_tool_execution_logs_entity_type", "tool_execution_logs", ["entity_type"], schema=schema)
    op.create_index("ix_tool_execution_logs_request_id", "tool_execution_logs", ["request_id"], schema=schema)
    op.create_index("ix_tool_execution_logs_created_at", "tool_execution_logs", ["created_at"], schema=schema)
    op.create_index("ix_tool_execution_logs_org_created", "tool_execution_logs", ["organization_id", "created_at"], schema=schema)


def downgrade() -> None:
    schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    for table in [
        "tool_execution_logs", "tasks", "integration_capability_defaults",
        "organization_integrations", "fileprocessor_jobs", "files", "file_types",
        "entity_events", "entity_state", "entity_relations", "entities",
        "agent_trace_events", "agent_trace_runs", "agent_messages",
        "agent_sessions", "agent_definitions",
    ]:
        op.drop_table(table, schema=schema)
