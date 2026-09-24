"""Request schemas for the llm module."""

from __future__ import annotations

from typing import Any, Self

from pydantic import Field, model_validator

from common.data_model import BaseModel as PydanticBaseModel
from llm.models.interface import (
    normalize_execution_provider,
    validate_feature,
    validate_model_name,
    validate_organization_id,
)


class LlmStatusRequest(PydanticBaseModel):
    request_id: str | None = None

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        self.request_id = str(self.request_id).strip() or None if self.request_id is not None else None
        return self


class LlmAvailableModelsRequest(PydanticBaseModel):
    organization_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        self.organization_id = validate_organization_id(self.organization_id or "", allow_none=True)
        return self


class LlmRuntimeResolutionRequest(PydanticBaseModel):
    organization_id: str = Field(..., min_length=1)
    feature: str = Field(..., min_length=1)
    model_override: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        self.organization_id = str(validate_organization_id(self.organization_id))
        self.feature = validate_feature(str(self.feature))
        if self.model_override is not None:
            self.model_override = validate_model_name(str(self.model_override), field_name="model_override")
        return self


class LlmServiceRequest(PydanticBaseModel):
    provider: str = Field(default="lite_llm", min_length=1)
    model_name: str | None = Field(default=None, min_length=1)
    organization_id: str | None = Field(default=None, min_length=1)
    feature: str | None = Field(default=None, min_length=1)
    api_key: str | None = Field(default=None, min_length=1)
    runtime_options: dict[str, Any] | None = None

    @model_validator(mode="after")
    def normalize_fields(self) -> Self:
        self.provider = normalize_execution_provider(self.provider).value
        if self.model_name is not None:
            self.model_name = validate_model_name(str(self.model_name))
        self.organization_id = validate_organization_id(self.organization_id or "", allow_none=True)
        if self.feature is not None:
            self.feature = validate_feature(str(self.feature))
        self.api_key = str(self.api_key).strip() or None if self.api_key is not None else None
        if self.runtime_options is not None:
            self.runtime_options = dict(self.runtime_options)
        return self


class AgentAiStatusRequest(LlmStatusRequest):
    """Backward-compatible alias for previous status request naming."""
