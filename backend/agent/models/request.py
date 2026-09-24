"""Request models for the agent module."""

from __future__ import annotations

from typing import Any, Self

from pydantic import Field, model_validator

from common.data_model import BaseModel as PydanticBaseModel
from common.utils import ensure_non_empty


class AgentSuggestion(PydanticBaseModel):
    label: str = Field(..., min_length=1)
    prompt: str = Field(..., min_length=1)


class AgentConstraints(PydanticBaseModel):
    max_iterations: int = Field(default=10, ge=1, le=20)
    require_approval: list[str] = Field(default_factory=list)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)


class AgentDefinitionCreate(PydanticBaseModel):
    name: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    display_name: str = Field(..., min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=512)
    system_prompt: str = Field(..., min_length=10)
    allowed_tools: list[str] | None = None
    constraints: AgentConstraints = Field(default_factory=AgentConstraints)
    suggestions: list[AgentSuggestion] = Field(default_factory=list)
    model_override: str | None = Field(default=None, max_length=128)
    is_active: bool = True


class AgentDefinitionUpdate(PydanticBaseModel):
    display_name: str | None = Field(default=None, max_length=128)
    description: str | None = Field(default=None, max_length=512)
    system_prompt: str | None = Field(default=None, min_length=10)
    allowed_tools: list[str] | None = None
    constraints: AgentConstraints | None = None
    suggestions: list[AgentSuggestion] | None = None
    model_override: str | None = Field(default=None, max_length=128)
    is_active: bool | None = None


class AgentChatRequest(PydanticBaseModel):
    agent: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1, max_length=10000)
    session_id: str | None = None
    context: dict[str, Any] | None = None

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        """Normalize trimmed string fields and defensive context defaults."""
        self.agent = ensure_non_empty(str(self.agent), "agent")
        self.message = ensure_non_empty(str(self.message), "message")
        self.session_id = (
            ensure_non_empty(str(self.session_id), "session_id") if self.session_id else None
        )
        self.context = dict(self.context or {}) if self.context is not None else None
        return self


class ActionApprovalRequest(PydanticBaseModel):
    action_id: str = Field(..., min_length=1)


class TraceRunListRequest(PydanticBaseModel):
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
    status: str | None = None
    agent_name: str | None = None
    run_type: str | None = None
    session_id: str | None = None


class AgentRunRequest(PydanticBaseModel):
    definition_id: str = Field(..., min_length=1)
    input: str = Field(..., min_length=1, max_length=10000)
    session_id: str | None = None
    context: dict[str, Any] | None = None
    # Optional uploaded-file id. When set, it is surfaced to tools via the tool
    # execution context (metadata["file_id"]) so read_document can resolve the
    # document without the id appearing in the prompt. Not part of request.context
    # (whose keys are whitelisted by the context service).
    document_id: str | None = None
    # Optional slug -> real file id map (e.g. {"file_1": "<uuid>"}), surfaced to
    # tools via metadata["file_slug_map"]. Lets a multi-file run (bulk_import's
    # read_job_document) resolve a model-supplied slug without ever putting the
    # real file id in the prompt/tool-call history — same reasoning as
    # document_id above, just for many files instead of one fixed document.
    file_slug_map: dict[str, str] | None = None

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        self.definition_id = ensure_non_empty(str(self.definition_id), "definition_id")
        self.input = ensure_non_empty(str(self.input), "input")
        self.session_id = (
            ensure_non_empty(str(self.session_id), "session_id") if self.session_id else None
        )
        self.context = dict(self.context or {}) if self.context is not None else None
        self.document_id = (
            ensure_non_empty(str(self.document_id), "document_id") if self.document_id else None
        )
        return self


class AgentResumeRequest(PydanticBaseModel):
    input: str | None = Field(default=None, max_length=10000)
    context: dict[str, Any] | None = None

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        self.input = ensure_non_empty(str(self.input), "input") if self.input else None
        self.context = dict(self.context or {}) if self.context is not None else None
        return self


class AgentSessionUpdateRequest(PydanticBaseModel):
    title: str = Field(..., min_length=1, max_length=256)

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        self.title = ensure_non_empty(self.title, "title")
        return self
