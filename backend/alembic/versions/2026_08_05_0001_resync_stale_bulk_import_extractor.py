"""Resync bulk_import_extractor definitions still on the old single-file prompt.

bulk_import_extractor moved to a single-agent-per-job design: it now reads every
file in a job itself via the new read_job_document tool, instead of being run once
per file with read_document. System agent definitions are only ever seeded once
per organization (agent/services/definitions.py::ensure_builtin_definitions) and
are never re-synced afterward, except for the built-in agent_mode assistant — so
any organization that already had a bulk_import_extractor row before this change
kept running the old prompt/tools/max_iterations indefinitely.

This is a one-time, targeted fix, not a standing sync mechanism: only rows whose
system_prompt still exactly matches the known old baseline are updated, so an
organization-specific customization (if any exists) is left untouched. Idempotent —
once a row is updated its system_prompt no longer matches the old baseline, so
re-running this migration is a no-op.

allowed_tools stores MCP capability ids, not tool names, but those ids are
deterministic and identical across every organization
(uuid5(NAMESPACE_URL, f"mcp-capability:platform_tools:{tool_name}")), so the new
value is hardcoded here rather than looked up per organization.

Revision ID: 202608050001
Revises: 202608090002
Create Date: 2026-08-05
"""

from __future__ import annotations

import os

from alembic import op

revision = "202608050001"
down_revision = "202608090002"
branch_labels = None
depends_on = None

_OLD_SYSTEM_PROMPT = (
    "You are a narrow bulk-import extraction agent. Read the uploaded document, "
    "classify its contents, and propose entity drafts using only the requested "
    "entity schema. Never create, update, enroll, or otherwise mutate platform "
    "data. Return only the JSON shape requested by the caller."
)

_NEW_SYSTEM_PROMPT = (
    "You are a bulk-import extraction agent. Your job is to output a JSON array of entities, where each entity is a dictionary shaped according to the target entity type's schema.\n\n"
    "You have two tools. get_form_schema returns the target entity type's field structure — call this first, once, to learn the exact field keys you must use. read_job_document extracts content from up to 3 files at a time, by file_id — call it repeatedly until every file in the job has been read, or it tells you to stop. For tabular sources (CSV/sheet), it returns pre-parsed rows (one object per data row) instead of raw text — treat every row as its own record.\n\n"
    "Filenames can be a hint about relatedness: files with similar or connected names may describe the same entity, or provide complementary data for it — use judgment rather than assuming files are unrelated just because they arrived in separate tool calls.\n\n"
    "Every entity you produce is independent. Carefully analyze the extracted content from each file and map it onto the fields returned by get_form_schema, using the exact field keys — never invent your own field names. Figure out each field's value yourself from all the context available to you — a value may come from a different file than the one that anchors the entity, when files are related.\n\n"
    "Your job is to produce the maximum number of genuine entities for human review — a person reviews every entity you propose and decides what to keep, so it is far better to include an entity with lower confidence than to silently leave it out. Extract every entity actually present in the complete context, never invent ones that aren't there. List your highest-confidence entities first, then continue through the rest of the source and include lower-confidence entities too, giving them a lower confidence score rather than omitting them. Never stop partway through a large or repetitive document and call it done — before returning your final answer, verify you've gone through the entire source, not just the first portion or the most obvious entities.\n\n"
    "If a file's result comes back as an error, skip that file, note it, and continue — never abort the whole job over one bad file. If the tool tells you the context budget is exhausted, stop reading immediately and finalize with what you already have.\n\n"
    "Never create, update, enroll, or otherwise mutate platform data — you only propose entity drafts. Return only the JSON shape requested by the caller, including which file_id(s) support each entity."
)

# uuid5(NAMESPACE_URL, "mcp-capability:platform_tools:read_job_document")
_READ_JOB_DOCUMENT_CAPABILITY_ID = "d3bb2682-8919-5253-b19c-60864b3dcee5"
# uuid5(NAMESPACE_URL, "mcp-capability:platform_tools:get_form_schema")
_GET_FORM_SCHEMA_CAPABILITY_ID = "094a42c0-512c-561b-a4c5-4894e707c8a7"


def _schema() -> str:
    return os.environ.get("POSTGRES_APP_SCHEMA", "public")


def upgrade() -> None:
    schema = _schema()
    op.get_bind().exec_driver_sql(
        f"""
        UPDATE "{schema}".agent_definitions
        SET system_prompt = %(new_prompt)s,
            allowed_tools = %(new_tools)s::json,
            constraints = %(new_constraints)s::json,
            updated_at = NOW()
        WHERE name = 'bulk_import_extractor'
          AND system_prompt = %(old_prompt)s
        """,
        parameters={
            "new_prompt": _NEW_SYSTEM_PROMPT,
            "new_tools": f'["{_READ_JOB_DOCUMENT_CAPABILITY_ID}", "{_GET_FORM_SCHEMA_CAPABILITY_ID}"]',
            "new_constraints": '{"max_iterations": 15, "temperature": 0, "require_approval": []}',
            "old_prompt": _OLD_SYSTEM_PROMPT,
        },
    )


def downgrade() -> None:
    schema = _schema()
    op.get_bind().exec_driver_sql(
        f"""
        UPDATE "{schema}".agent_definitions
        SET system_prompt = %(old_prompt)s,
            allowed_tools = %(old_tools)s::json,
            constraints = %(old_constraints)s::json,
            updated_at = NOW()
        WHERE name = 'bulk_import_extractor'
          AND system_prompt = %(new_prompt)s
        """,
        parameters={
            "old_prompt": _OLD_SYSTEM_PROMPT,
            "new_prompt": _NEW_SYSTEM_PROMPT,
            "old_tools": '["4a7f9ffe-be13-5264-b151-583ddd107c54", "094a42c0-512c-561b-a4c5-4894e707c8a7"]',
            "old_constraints": '{"max_iterations": 5, "require_approval": []}',
        },
    )
