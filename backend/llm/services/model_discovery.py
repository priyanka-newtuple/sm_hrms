"""LiteLLM-backed provider model discovery."""

from __future__ import annotations

from typing import Any

import litellm


class LiteLLMModelDiscoveryService:
    """Discover provider models without owning model execution."""

    @staticmethod
    def discover_provider_models(
        provider: str,
        *,
        credentials: dict[str, Any] | None = None,
        check_provider_endpoint: bool = True,
    ) -> list[str]:
        creds = credentials or {}
        normalized_provider = str(provider or "").strip().lower()

        if normalized_provider in {"openai", "anthropic", "gemini"}:
            return list(
                litellm.get_valid_models(
                    custom_llm_provider=normalized_provider,
                    api_key=str(creds.get("api_key") or ""),
                    api_base=str(
                        creds.get("api_base") or creds.get("endpoint") or ""
                    )
                    or None,
                    check_provider_endpoint=check_provider_endpoint,
                )
            )

        if normalized_provider == "azure":
            deployment_name = str(creds.get("deployment_name") or "").strip()
            return [f"azure/{deployment_name}"] if deployment_name else []

        if normalized_provider == "azure_foundry":
            endpoint = str(creds.get("endpoint") or "").strip()
            api_key = str(creds.get("api_key") or "").strip()
            if not endpoint or not api_key:
                return []
            try:
                from llm.services.azure_foundry import list_foundry_model_names

                models = list_foundry_model_names(endpoint, api_key)
            except ImportError:
                return []
            return [f"foundry/{model}" for model in models]

        if normalized_provider == "bedrock":
            try:
                from llm.services.bedrock import list_bedrock_model_names

                models = list_bedrock_model_names(creds)
            except ImportError:
                return []
            return [f"bedrock/{model}" for model in models]

        return []
