"""Shared behavior for provider-specific agent-model services."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from exceptions import ServiceError
from llm.models.interface import AgentModelBuildContext


class AgentModelServiceBase(ABC):
    """Base service for constructing one family of Agents SDK models."""

    requires_api_key = True

    @abstractmethod
    def build(self, context: AgentModelBuildContext) -> Any:
        """Construct a provider-specific Agents SDK model."""

    @staticmethod
    def required_api_key(context: AgentModelBuildContext) -> str:
        api_key = str(context.api_key or "").strip()
        if not api_key:
            raise ServiceError(
                "No LLM API key is configured for this organization. "
                "Add one under Settings -> Integrations."
            )
        return api_key
