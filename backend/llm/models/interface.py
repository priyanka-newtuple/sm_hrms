"""Interface models and contracts for the llm module."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import ConfigDict

from common.data_model import BaseModel as PydanticBaseModel, LLMProvider


class LlmFeature(str):
    PLAYBOOK_AGENT = "playbook_agent"
    RESUME_EXTRACTION = "resume_extraction"
    GENERAL = "general"


FEATURE_ALIASES = {
    "playbook_agent": LlmFeature.PLAYBOOK_AGENT,
    "resume_extraction": LlmFeature.RESUME_EXTRACTION,
    "general": LlmFeature.GENERAL,
    "file_processing": LlmFeature.GENERAL,
}


class LlmStatusContract(PydanticBaseModel):
    """Contract for module status payloads."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    module: str
    status: str
    started: bool


class LlmRuntimeContract(PydanticBaseModel):
    """Resolved runtime configuration for one LLM request."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    feature: str
    model: str
    provider: str
    api_key_found: bool
    used_fallback: bool


class LlmModelLookupService(Protocol):
    """Protocol for LLM model and credential lookups."""

    def get_default_model(self) -> str: ...

    def get_model_for_feature(self, organization_id: str, feature: str) -> str | None: ...

    def get_api_key_for_model(self, organization_id: str | None, model: str) -> str | None: ...

    def get_provider_for_model(self, model: str) -> LLMProvider: ...


class LlmIntegrationCredentialsService(Protocol):
    """Protocol for organization-scoped integration credential lookups."""

    def get_llm_credentials(self, organization_id: str, provider: str) -> dict[str, Any]: ...

    def get_provider_credentials(self, organization_id: str, provider: str) -> dict[str, Any]: ...

    def list_organization_integrations(self, organization_id: str) -> Any: ...


class LlmAuthorizationService(Protocol):
    """Protocol for cross-organization access checks."""

    def check_access(self, payload: dict[str, Any]) -> Any: ...


@dataclass(frozen=True)
class AgentModelBuildContext:
    """Provider-neutral inputs required to construct an Agents SDK model."""

    organization_id: str | None
    model_name: str
    provider: LLMProvider
    credentials: dict[str, Any]
    api_key: str | None
    runtime_kwargs: dict[str, Any]


class AgentModelService(Protocol):
    """Contract implemented by provider-specific agent-model services."""

    requires_api_key: bool

    def build(self, context: AgentModelBuildContext) -> Any: ...


def normalize_feature(feature: str) -> str | None:
    """Normalize caller-facing feature identifiers."""

    normalized = str(feature or "").strip().lower()
    return FEATURE_ALIASES.get(normalized)


def validate_feature(feature: str) -> str:
    """Validate and normalize a caller-facing feature identifier."""

    normalized = normalize_feature(feature)
    if normalized is None:
        raise ValueError("feature must be one of: playbook_agent, resume_extraction, general")
    return normalized


def validate_organization_id(organization_id: str, *, allow_none: bool = False) -> str | None:
    """Validate and normalize an organization id."""

    normalized = str(organization_id or "").strip()
    if not normalized:
        if allow_none:
            return None
        raise ValueError("organization_id must be a non-empty string")
    return normalized


def validate_model_name(model_name: str, *, field_name: str = "model_name") -> str:
    """Validate and normalize a model identifier."""

    normalized = str(model_name or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def normalize_execution_provider(provider: str | LLMProvider | None) -> LLMProvider:
    """Normalize runtime execution provider selection."""

    if isinstance(provider, LLMProvider):
        return provider
    normalized = str(provider or "").strip().lower()
    try:
        return LLMProvider(normalized)
    except Exception:
        return LLMProvider.lite_llm
