"""Interface models and execution contracts for tools."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import ConfigDict, Field

from common.data_model import BaseModel as PydanticBaseModel

# `read_job_document` tool limits (bulk-import single-agent pipeline). One agent run
# covers a whole job's files, so these guard against blowing the model's context
# window across many files in one conversation — see
# design_docs/tony_bulk_import_single_agent_pipeline.md.
READ_JOB_DOCUMENT_MAX_FILES_PER_CALL = 3
READ_JOB_DOCUMENT_PER_FILE_CHAR_CAP = 80_000
READ_JOB_DOCUMENT_RUN_BUDGET_CHARS = 320_000
# Bound on how many in-flight runs' budget counters are tracked in memory at once,
# so a long-lived process can't accumulate an unbounded dict of finished runs.
READ_JOB_DOCUMENT_TRACKED_RUNS_LIMIT = 500


class ToolDescriptorContract(PydanticBaseModel):
    """Describe one shared tool in the canonical catalog."""

    model_config = ConfigDict(frozen=True)

    name: str
    display_name: str
    description: str
    category: str
    risk_level: str
    default_enabled: bool = True
    # Whether this tool is surfaced to agents as an MCP capability. Defaults to
    # False so exposure to the agent runtime is an explicit, opt-in decision made
    # where the tool is defined.
    mcp_exposed: bool = False
    # Whether invoking this tool changes data. Drives the default approval policy
    # for the seeded MCP capability. Set explicitly rather than inferred from
    # risk_level (e.g. add_stage_comment is low-risk but still mutating).
    is_mutating: bool = False
    parameters: dict[str, Any] = Field(default_factory=dict)


class ToolPresetContract(PydanticBaseModel):
    """Describe one named preset of shared tools."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    tools: list[str] = Field(default_factory=list)


class ToolExecutionContext(PydanticBaseModel):
    """Carry shared execution context for a tool call."""

    run_id: str | None = None
    session_id: str | None = None
    organization_id: str | None = None
    user_id: str | None = None
    actor_id: str | None = None
    actor_type: str = "AGENT"
    roles: list[str] = Field(default_factory=list)
    entity_id: str | None = None
    entity_type: str | None = None
    source: str = "agent"
    request_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolExecutionResult(PydanticBaseModel):
    """Represent the normalized result of one tool execution."""

    execution_id: str | None = None
    execution_backend: str | None = None
    success: bool
    tool_name: str
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    duration_ms: int = 0


class ToolExecutionLogContract(PydanticBaseModel):
    """Persisted audit record for one tool execution attempt."""

    id: str
    organization_id: str
    user_id: str | None = None
    actor_id: str | None = None
    actor_type: str | None = None
    source: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    success: bool
    error: str | None = None
    duration_ms: int = 0
    execution_backend: str
    run_id: str | None = None
    session_id: str | None = None
    entity_id: str | None = None
    entity_type: str | None = None
    request_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata_json")
    created_at: datetime

