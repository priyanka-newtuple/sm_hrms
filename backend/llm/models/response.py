"""Response models for llm."""

from __future__ import annotations

from common.data_model import BaseModel as PydanticBaseModel

from pydantic import Field


class LlmStatusResponse(PydanticBaseModel):
    """Module health status response."""

    module: str = Field(..., min_length=1, description="Module name")
    status: str = Field(..., min_length=1, description="Health status")
    started: bool = Field(..., description="Whether manager startup ran")

    def to_dict(self) -> dict[str, object]:
        return self.model_dump()


class LlmRuntimeResolutionResponse(PydanticBaseModel):
    """Resolved runtime configuration for one LLM workload."""

    feature: str = Field(..., min_length=1, description="Normalized feature name")
    model: str = Field(..., min_length=1, description="Resolved model identifier")
    provider: str = Field(..., min_length=1, description="Execution provider")
    api_key_found: bool = Field(..., description="Whether a provider key was resolved")
    used_fallback: bool = Field(..., description="Whether the default model fallback was used")


class LlmModelInfoResponse(PydanticBaseModel):
    """Information about an available model."""

    id: str = Field(..., min_length=1, description="Executable model identifier")
    name: str = Field(..., min_length=1, description="Human-readable model name")
    max_tokens: int | None = Field(default=None, description="Maximum output tokens if known")
    input_cost_per_token: float | None = Field(default=None, description="Input token cost if known")
    output_cost_per_token: float | None = Field(default=None, description="Output token cost if known")


class LlmProviderModelsResponse(PydanticBaseModel):
    """Models available for one provider."""

    provider: str = Field(..., min_length=1, description="Provider identifier")
    provider_name: str = Field(..., min_length=1, description="Provider display name")
    models: list[LlmModelInfoResponse] = Field(default_factory=list)


class LlmAvailableModelsResponse(PydanticBaseModel):
    """Available models grouped by provider for one organization."""

    providers: list[LlmProviderModelsResponse] = Field(default_factory=list)
    has_validated_keys: bool = Field(..., description="Whether at least one configured provider yielded models")


class AgentAiStatusResponse(LlmStatusResponse):
    """Backward-compatible alias for previous status model naming."""
