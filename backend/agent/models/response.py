"""Response models for the agent module."""

from __future__ import annotations

from datetime import datetime

from pydantic import ConfigDict, Field

from common.data_model import BaseModel as PydanticBaseModel


class AgentDefinitionResponse(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    definition_id: str
    name: str
    display_name: str
    description: str | None = None
    system_prompt: str
    allowed_tools: list[str] | None = None
    constraints: dict[str, object] = Field(default_factory=dict)
    suggestions: list[dict[str, str]] = Field(default_factory=list)
    model_override: str | None = None
    is_active: bool
    is_system: bool
    organization_id: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class AgentDefinitionListResponse(PydanticBaseModel):
    definition_id: str
    name: str
    display_name: str
    description: str | None = None
    is_active: bool
    is_system: bool
    tool_count: int = 0
    approval_count: int = 0
    suggestion_count: int = 0


class ToolCallInfo(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    tool: str
    args: dict[str, object] = Field(default_factory=dict)
    result: dict[str, object] | None = None
    success: bool
    duration_ms: int
    tool_call_id: str | None = None


class PendingActionResponse(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    action_id: str
    tool: str
    args: dict[str, object] = Field(default_factory=dict)
    description: str
    status: str = "pending"
    result: dict[str, object] | None = None


class AgentChatResponse(PydanticBaseModel):
    success: bool
    session_id: str
    message_id: str
    content: str
    tool_calls: list[ToolCallInfo] = Field(default_factory=list)
    pending_actions: list[PendingActionResponse] = Field(default_factory=list)
    tokens_used: int = 0
    error: str | None = None


class ActionApprovalResponse(PydanticBaseModel):
    success: bool
    action_id: str
    result: dict[str, object] | None = None
    error: str | None = None


class AgentSessionResponse(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: str
    definition_id: str | None = None
    agent_name: str | None = None
    title: str | None = None
    context: dict[str, object] | None = None
    message_count: int = 0
    total_tokens: int = 0
    created_at: datetime
    updated_at: datetime


class AgentMessageResponse(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    message_id: str
    role: str
    content: str
    tool_calls: list[dict[str, object]] | None = None
    pending_actions: list[dict[str, object]] | None = None
    tokens_used: int = 0
    created_at: datetime


class SessionWithMessagesResponse(PydanticBaseModel):
    session: AgentSessionResponse
    messages: list[AgentMessageResponse] = Field(default_factory=list)


class ToolInfo(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    description: str
    parameters: dict[str, object] = Field(default_factory=dict)


class ToolManifestResponse(PydanticBaseModel):
    tools: list[ToolInfo] = Field(default_factory=list)


class AgentTraceEventResponse(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    seq: int
    kind: str
    payload: dict[str, object] | None = None
    created_at: datetime


class AgentTraceRunListItem(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    agent_name: str
    run_type: str
    status: str
    model: str | None = None
    input_message: str | None = None
    session_id: str | None = None
    message_id: str | None = None
    user_id: str | None = None
    error: str | None = None
    tokens_used: int = 0
    iterations: int | None = None
    duration_ms: int | None = None
    started_at: datetime
    completed_at: datetime | None = None


class AgentTraceRunListResponse(PydanticBaseModel):
    items: list[AgentTraceRunListItem] = Field(default_factory=list)
    total: int = 0


class AgentTraceSessionListItem(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: str
    agent_name: str
    latest_run_id: str
    latest_message_id: str | None = None
    latest_status: str
    latest_input_message: str | None = None
    user_id: str | None = None
    model: str | None = None
    run_count: int = 0
    total_tokens: int = 0
    total_duration_ms: int = 0
    first_started_at: datetime
    last_started_at: datetime
    last_completed_at: datetime | None = None


class AgentTraceSessionListResponse(PydanticBaseModel):
    items: list[AgentTraceSessionListItem] = Field(default_factory=list)
    total: int = 0


class AgentTraceRunDetailResponse(AgentTraceRunListItem):
    context: dict[str, object] | None = None
    events: list[AgentTraceEventResponse] = Field(default_factory=list)


class AgentRunResponse(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True, serialize_by_alias=True)

    run_id: str
    definition_id: str
    session_id: str | None = None
    status: str
    input: str = Field(validation_alias="input_text", serialization_alias="input")
    output: str | None = Field(
        default=None, validation_alias="output_text", serialization_alias="output"
    )
    error: str | None = None
    metadata: dict[str, object] = Field(
        default_factory=dict,
        validation_alias="backend_metadata",
        serialization_alias="metadata",
    )
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime | None = None


class AgentRunListResponse(PydanticBaseModel):
    items: list[AgentRunResponse] = Field(default_factory=list)
    total: int = 0
