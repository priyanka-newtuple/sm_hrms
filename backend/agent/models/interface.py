"""Interface models and contracts for the agent module."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import ConfigDict, Field

from common.data_model import BaseModel as PydanticBaseModel

# Max characters of the user input used as a new session's title.
SESSION_TITLE_MAX_LENGTH = 80


class AgentSuggestionContract(PydanticBaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    label: str
    prompt: str


class AgentConstraintContract(PydanticBaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    max_iterations: int = 10
    require_approval: list[str] = Field(default_factory=list)
    temperature: float | None = None


class AgentTemplateContract(PydanticBaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    name: str
    display_name: str
    description: str | None = None
    system_prompt: str
    allowed_tools: list[str] | None = None
    constraints: AgentConstraintContract = Field(default_factory=AgentConstraintContract)
    suggestions: list[AgentSuggestionContract] = Field(default_factory=list)
    model_override: str | None = None
    is_active: bool = True
    is_system: bool = True


class AgentDefinitionContract(PydanticBaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    definition_id: str
    name: str
    display_name: str
    description: str | None = None
    system_prompt: str
    allowed_tools: list[str] | None = None
    constraints: dict[str, Any] = Field(default_factory=dict)
    suggestions: list[dict[str, str]] = Field(default_factory=list)
    model_override: str | None = None
    is_active: bool = True
    is_system: bool = False
    organization_id: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class AgentSessionContract(PydanticBaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    session_id: str
    definition_id: str | None = None
    user_id: str
    organization_id: str
    context: dict[str, Any] | None = None
    title: str | None = None
    total_tokens: int = 0
    message_count: int = 0
    created_at: datetime
    updated_at: datetime


class RequestContext(PydanticBaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    organization_id: str
    user_id: str | None = None
    roles: list[str] = Field(default_factory=list)
    request_id: str | None = None
    source: Literal["api", "background_job", "system"] = "api"


class RuntimeContext(PydanticBaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    organization_id: str
    user_id: str | None = None
    roles: list[str] = Field(default_factory=list)
    request_id: str | None = None
    source: str = "api"
    job_id: str | None = None


class AgentSessionContext(PydanticBaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    session_id: str
    definition_id: str | None = None
    recent_messages: list[dict[str, Any]] = Field(default_factory=list)
    context: dict[str, Any] | None = None


class DomainContext(PydanticBaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    entities: list[dict[str, Any]] = Field(default_factory=list)
    workflow_state: dict[str, Any] = Field(default_factory=dict)
    audit_events: list[dict[str, Any]] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)


class AgentExecutionContext(PydanticBaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    request: RequestContext
    runtime: RuntimeContext
    session: AgentSessionContext | None = None
    domain: DomainContext = Field(default_factory=DomainContext)
    memory: dict[str, Any] | None = None


class AgentRuntimeSpec(PydanticBaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    definition_id: str
    key: str
    name: str
    description: str | None = None
    instructions: str
    model: str
    max_turns: int = Field(default=10, ge=1, le=20)
    tool_ids: list[str] = Field(default_factory=list)
    # When true, the runtime grants EVERY platform capability (bypassing the
    # per-org enablement gate) instead of resolving tool_ids — used only by the
    # built-in Agent Mode assistant.
    all_tools: bool = False
    handoff_definition_ids: list[str] = Field(default_factory=list)
    is_background_enabled: bool = False
    # From the definition's constraints.temperature, when set — opt-in per
    # definition, defaults to None (the model's own default) for every existing
    # agent so this is additive, not a platform-wide behavior change.
    temperature: float | None = None


class AgentRunContract(PydanticBaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    run_id: str
    organization_id: str
    definition_id: str
    session_id: str | None = None
    user_id: str | None = None
    status: str
    input_text: str
    output_text: str | None = None
    error: str | None = None
    backend_metadata: dict[str, Any] = Field(default_factory=dict)
    execution_context: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None


class RuntimeBackendRunRequest(PydanticBaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True, arbitrary_types_allowed=True)

    run_id: str
    runtime_spec: AgentRuntimeSpec
    input_text: str
    execution_context: AgentExecutionContext
    tools: list[Any] = Field(default_factory=list)
    # In-memory only (never persisted): base64 image data URLs to attach to the
    # user message for vision-capable models. Resolved + vision-guarded by the
    # runtime before this request is built.
    input_images: list[str] = Field(default_factory=list)


class RuntimeBackendResumeRequest(PydanticBaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True, arbitrary_types_allowed=True)

    run: AgentRunContract
    input_text: str | None = None
    execution_context: AgentExecutionContext
    tools: list[Any] = Field(default_factory=list)


class RuntimeBackendResult(PydanticBaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    status: Literal["completed", "waiting_for_approval", "failed"] = "completed"
    output_text: str | None = None
    error: str | None = None
    tokens_used: int = 0
    backend_metadata: dict[str, Any] = Field(default_factory=dict)


class ToolCallContract(PydanticBaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    success: bool = True
    duration_ms: int = 0
    tool_call_id: str | None = None


class PendingActionContract(PydanticBaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    action_id: str
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    description: str
    status: str = "pending"
    result: dict[str, Any] | None = None
    approved_by: str | None = None
    approved_at: str | None = None
    rejected_by: str | None = None
    rejected_at: str | None = None


class AgentMessageContract(PydanticBaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    message_id: str
    session_id: str
    role: str
    content: str
    tool_calls: list[dict[str, Any]] | None = None
    pending_actions: list[dict[str, Any]] | None = None
    tokens_used: int = 0
    created_at: datetime


class AgentTraceEventContract(PydanticBaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: str
    run_id: str
    seq: int
    kind: str
    payload: dict[str, Any] | None = None
    created_at: datetime


class AgentTraceRunContract(PydanticBaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: str
    organization_id: str
    user_id: str | None = None
    agent_name: str
    run_type: str
    status: str
    model: str | None = None
    input_message: str | None = None
    session_id: str | None = None
    message_id: str | None = None
    context: dict[str, Any] | None = None
    error: str | None = None
    tokens_used: int = 0
    iterations: int | None = None
    duration_ms: int | None = None
    started_at: datetime
    completed_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None


class AgentTraceSessionContract(PydanticBaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    session_id: str
    organization_id: str
    user_id: str | None = None
    agent_name: str
    latest_run_id: str
    latest_message_id: str | None = None
    latest_status: str
    latest_input_message: str | None = None
    model: str | None = None
    run_count: int = 0
    total_tokens: int = 0
    total_duration_ms: int = 0
    first_started_at: datetime
    last_started_at: datetime
    last_completed_at: datetime | None = None


class EphemeralAgentConfigContract(PydanticBaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    name: str
    system_prompt: str
    allowed_tools: list[str] | None = None
    require_approval: list[str] = Field(default_factory=list)
    max_iterations: int = 10
    model_override: str | None = None


class AgentRuntimeResultContract(PydanticBaseModel):
    success: bool
    content: str
    tool_calls: list[ToolCallContract] = Field(default_factory=list)
    pending_actions: list[PendingActionContract] = Field(default_factory=list)
    error: str | None = None
    tokens_used: int = 0
    iterations: int = 0
    model: str | None = None
    trace_events: list[dict[str, Any]] = Field(default_factory=list)
