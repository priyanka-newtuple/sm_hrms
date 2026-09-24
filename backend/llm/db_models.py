"""Persistence adapters for the llm module."""

from __future__ import annotations

from typing import Any

from common.configuration import get_configuration
from common.data_model import LLMProvider
from llm.models.interface import normalize_feature


class LlmModelService:
    """Persistence helpers for llm runtime configuration."""

    def __init__(self, database_service_manager: Any, config: Any = None) -> None:
        self.database_manager = database_service_manager
        self.database_service_manager = database_service_manager
        self.config = config
        self.current_db = (
            self.database_manager.postgres_db_service()
            if self.database_manager and hasattr(self.database_manager, "postgres_db_service")
            else None
        )
        self.current_db_engine = getattr(self.current_db, "engine", None)
        self.module_name = "llm"

    def _cfg_root(self) -> Any:
        if self.config is None:
            return get_configuration()
        return self.config._configuration if hasattr(self.config, "_configuration") else self.config

    @staticmethod
    def _clean_value(value: object, *, placeholders: set[str] | None = None) -> str | None:
        token = str(value or "").strip().strip('"')
        if not token:
            return None
        if token.startswith(("SAMPLE_", "YOUR_")):
            return None
        if placeholders and token in placeholders:
            return None
        return token

    def get_default_model(self) -> str:
        """Return the default model identifier for LLM execution.

        Returns:
            Default model id (e.g. `gpt-4o-mini`, `claude-sonnet-4-20250514`).
        """
        cfg_root = self._cfg_root()
        runtime_cfg = getattr(cfg_root, "runtime_configuration", None)
        if runtime_cfg is None:
            return "gpt-4o-mini"
        return self._clean_value(getattr(runtime_cfg, "litellm_model", "")) or "gpt-4o-mini"

    def get_model_for_feature(self, organization_id: str, feature: str) -> str | None:
        """Resolve a model identifier for a given LLM feature.

        Note:
            The modular backend does not depend on legacy `backend/app` feature
            configuration. Feature-to-model resolution is handled via
            per-request overrides (or defaults).

        Args:
            organization_id: Organization id (reserved for future org-scoped config).
            feature: Caller-facing feature identifier (e.g. `playbook_agent`).

        Returns:
            Model id if configured for the feature; otherwise None.
        """
        _ = organization_id
        normalized_feature = normalize_feature(feature)
        if normalized_feature is None:
            return None
        _ = normalized_feature
        return None

    def get_api_key_for_model(self, organization_id: str | None, model: str) -> str | None:
        """Resolve an API key for a given model from environment configuration.

        Org-scoped keys now live in ``organization_integrations`` and are resolved
        by the LLM service manager. This method provides only the
        environment-variable fallback.

        Args:
            organization_id: Optional organization id (unused; kept for interface
                compatibility).
            model: Model identifier.

        Returns:
            API key if configured in the environment; otherwise None.
        """
        model = str(model or "").strip()
        if not model:
            return None
        provider = self.get_provider_for_model(model)
        return self._api_key_from_config(provider)

    def get_provider_for_model(self, model: str) -> LLMProvider:
        """Infer the provider for a model identifier using naming conventions.

        Args:
            model: Model identifier.

        Returns:
            Inferred provider enum.
        """
        if not model:
            return LLMProvider.lite_llm
        normalized_model = str(model).strip().lower()
        if normalized_model.startswith(("foundry/", "azure_foundry/")):
            return LLMProvider.azure_foundry
        if normalized_model.startswith("azure/") or "azure" in normalized_model:
            return LLMProvider.azure_openai
        if normalized_model.startswith("bedrock/") or "bedrock" in normalized_model:
            return LLMProvider.bedrock
        if "gemini" in normalized_model or normalized_model.startswith("vertex_ai/"):
            return LLMProvider.gemini_ai
        if normalized_model.startswith(("gpt-", "chatgpt-", "o1", "o3", "o4", "text-embedding-")):
            return LLMProvider.openai
        if normalized_model.startswith("claude") or "anthropic" in normalized_model:
            return LLMProvider.anthropic_ai
        if "perplexity" in normalized_model or "sonar" in normalized_model:
            return LLMProvider.perplexity_ai
        return LLMProvider.lite_llm

    def _api_key_from_config(self, provider: LLMProvider) -> str | None:
        cfg_root = self._cfg_root()
        placeholders = {
            "SAMPLE_OPENAI_API_KEY",
            "SAMPLE_ANTHROPIC_API_KEY",
            "SAMPLE_GEMINI_API_KEY",
            "SAMPLE_PERPLEXITY_API_KEY",
            "SAMPLE_AZURE_API_KEY",
            "YOUR_OPENAI_API_KEY",
            "YOUR_ANTHROPIC_API_KEY",
            "YOUR_GEMINI_API_KEY",
            "YOUR_PERPLEXITY_API_KEY",
            "YOUR_AZURE_API_KEY",
        }
        if provider == LLMProvider.openai:
            return self._clean_value(getattr(getattr(cfg_root, "openai_configuration", None), "api_key", ""), placeholders=placeholders)
        if provider == LLMProvider.anthropic_ai:
            return self._clean_value(getattr(getattr(cfg_root, "anthropicai_configuration", None), "api_key", ""), placeholders=placeholders)
        if provider == LLMProvider.gemini_ai:
            return self._clean_value(getattr(getattr(cfg_root, "geminiai_configuration", None), "api_key", ""), placeholders=placeholders)
        if provider == LLMProvider.perplexity_ai:
            return self._clean_value(getattr(getattr(cfg_root, "perplexityai_configuration", None), "api_key", ""), placeholders=placeholders)
        if provider == LLMProvider.azure_openai:
            return self._clean_value(getattr(getattr(cfg_root, "azureai_configuration", None), "api_key", ""), placeholders=placeholders)
        if provider == LLMProvider.azure_foundry:
            return None
        return None
