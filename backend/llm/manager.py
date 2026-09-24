"""Business logic manager for llm runtime resolution and discovery."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import litellm

from common.auth import actor_str
from common.data_model import LLMProvider
from common.enums import ModuleStatus
from common.logger import logger
from exceptions import AuthorizationError, ServiceError, ValidationError
from llm.models.interface import (
    AgentModelBuildContext,
    AgentModelService,
    LlmAuthorizationService,
    LlmIntegrationCredentialsService,
    LlmModelLookupService,
    normalize_feature,
)
from llm.models.response import (
    LlmAvailableModelsResponse,
    LlmModelInfoResponse,
    LlmProviderModelsResponse,
    LlmRuntimeResolutionResponse,
    LlmStatusResponse,
)
from llm.services import default_agent_model_services
from llm.services.model_discovery import LiteLLMModelDiscoveryService

if TYPE_CHECKING:
    from llm.db_models import LlmModelService

DEFAULT_AGENT_CHAT_TIMEOUT = 600


class LlmServiceManager:
    """Business logic manager for llm runtime resolution and discovery."""

    def __init__(
        self,
        llm_db_model_service: LlmModelService | LlmModelLookupService,
        database_service_manager: Any = None,
        config: Any = None,
        auth_service_manager: LlmAuthorizationService | None = None,
        integrations_service_manager: LlmIntegrationCredentialsService | None = None,
        *dependencies,
    ) -> None:
        self.llm_db_model_service = llm_db_model_service
        self.db_model_service = llm_db_model_service
        self.model_service = llm_db_model_service
        self.database_service_manager = database_service_manager
        self.config = config
        self.dependencies = list(dependencies)
        self.auth_service_manager = auth_service_manager
        self.integrations_service_manager = integrations_service_manager
        self.agent_model_services: dict[
            LLMProvider, AgentModelService
        ] = default_agent_model_services()
        self.module_name = "llm"
        self._started = False

    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False

    def get_status(self) -> LlmStatusResponse:
        """Return the LLM module status.

        Returns:
            LlmStatusResponse.
        """
        return LlmStatusResponse(module=self.module_name, status=ModuleStatus.READY.value, started=self._started)

    def resolve_model_for_feature(self, organization_id: str, feature: str) -> str:
        """Resolve the configured model for a feature, with fallbacks.

        Args:
            organization_id: Organization id.
            feature: Feature identifier (e.g. `playbook_agent`).

        Returns:
            Model identifier.

        Raises:
            ValidationError: When the feature is invalid.
        """

        try:
            normalized_feature = normalize_feature(feature)
            default_model = self.db_model_service.get_default_model()
            if not organization_id or normalized_feature is None:
                return default_model
            resolved = self.db_model_service.get_model_for_feature(organization_id, normalized_feature)
            return resolved or default_model
        except ValidationError:
            raise
        except Exception as exc:
            logger.warning(f"resolve_model_for_feature failed org_id={organization_id} feature={feature}: {exc}")
            return self.db_model_service.get_default_model()

    def resolve_api_key_for_model(self, organization_id: str | None, model: str) -> str | None:
        """Resolve the API key for a model using integrations, org config, or env.

        Args:
            organization_id: Optional organization id.
            model: Model identifier.

        Returns:
            API key if configured; otherwise None.
        """

        if not model:
            return None
        try:
            provider = self.db_model_service.get_provider_for_model(model)
            credentials = self._resolve_provider_credentials(organization_id, provider)
            api_key = credentials.get("api_key")
            if api_key:
                return str(api_key)
            return self.db_model_service.get_api_key_for_model(organization_id, model)
        except Exception as exc:
            logger.warning(f"resolve_api_key_for_model failed org_id={organization_id} model={model}: {exc}")
            return None

    def _resolve_provider_credentials(
        self,
        organization_id: str | None,
        provider: LLMProvider,
    ) -> dict[str, Any]:
        if self.integrations_service_manager is None or not organization_id:
            return {}
        try:
            integration_provider = self._integration_provider_for_llm_provider(
                provider.value
            )
            if integration_provider is None:
                return {}
            return dict(
                self.integrations_service_manager.get_llm_credentials(
                    organization_id,
                    integration_provider,
                )
                or {}
            )
        except Exception as exc:
            logger.warning(
                "resolve_provider_credentials failed org_id=%s provider=%s: %s",
                organization_id,
                provider.value,
                exc,
            )
            return {}

    @staticmethod
    def _integration_provider_for_llm_provider(provider: str) -> str | None:
        return {
            LLMProvider.openai.value: "openai",
            LLMProvider.anthropic_ai.value: "anthropic",
            LLMProvider.gemini_ai.value: "google_gemini",
            LLMProvider.azure_openai.value: "azure_openai",
            LLMProvider.azure_foundry.value: "azure_foundry",
            LLMProvider.bedrock.value: "aws_bedrock",
        }.get(provider)

    def resolve_runtime_for_feature(
        self,
        organization_id: str,
        feature: str,
        model_override: str | None = None,
    ) -> LlmRuntimeResolutionResponse:
        """Resolve runtime configuration for a feature.

        Args:
            organization_id: Organization id.
            feature: Feature identifier.
            model_override: Optional model override.

        Returns:
            LlmRuntimeResolutionResponse.

        Raises:
            ValidationError: When feature is unsupported.
        """
        normalized_feature = normalize_feature(feature)
        if normalized_feature is None:
            raise ValidationError("Unsupported llm feature")
        default_model = self.db_model_service.get_default_model()
        model = model_override or self.resolve_model_for_feature(organization_id, normalized_feature)
        provider = self.db_model_service.get_provider_for_model(model)
        api_key = self.resolve_api_key_for_model(organization_id, model)
        return LlmRuntimeResolutionResponse(
            feature=normalized_feature,
            model=model,
            provider=provider.value,
            api_key_found=bool(api_key),
            used_fallback=model == default_model and model_override is None,
        )

    def build_agent_chat_model(
        self,
        *,
        organization_id: str | None,
        model_name: str,
        timeout: int | float | None = DEFAULT_AGENT_CHAT_TIMEOUT,
        tracing_disabled: bool | None = None,
        **runtime_kwargs: Any,
    ) -> Any:
        """Build a provider-native model behind the OpenAI Agents SDK contract.

        Agent runtime code delegates provider/model/client construction here so
        the LLM module remains the single owner of model, provider, credential,
        timeout, tracing, and provider-runtime resolution.

        The method name is retained for compatibility with existing callers.
        """
        if not model_name:
            raise ValidationError("model_name is required")
        kwargs = self._build_agent_runtime_kwargs(
            timeout=timeout,
            tracing_disabled=tracing_disabled,
            runtime_kwargs=runtime_kwargs,
        )
        provider = self._resolve_agent_provider(model_name)
        service = self.agent_model_services.get(provider)
        if service is None:
            raise ServiceError(
                f"No agent model service is registered for provider: {provider.value}"
            )
        credentials = self._resolve_provider_credentials(
            organization_id,
            provider,
        )
        api_key = str(credentials.get("api_key") or "").strip() or None
        if service.requires_api_key and not api_key:
            api_key = self.db_model_service.get_api_key_for_model(
                organization_id, model_name
            )
        context = AgentModelBuildContext(
            organization_id=organization_id,
            model_name=model_name,
            provider=provider,
            credentials=credentials,
            api_key=str(api_key).strip() if api_key else None,
            runtime_kwargs=kwargs,
        )
        return service.build(context)

    def _resolve_agent_provider(self, model_name: str) -> LLMProvider:
        provider = self.db_model_service.get_provider_for_model(model_name)
        if not isinstance(provider, LLMProvider):
            raise ServiceError(f"Unable to resolve llm provider for model: {model_name}")
        return provider

    def supports_param(self, model_name: str, param: str = "temperature") -> bool:
        """Return whether the given model accepts this OpenAI-style chat param.

        Backed by litellm's own model registry (`get_supported_openai_params`),
        already a dependency here. Defensive by design: any lookup failure
        (unrecognized model, litellm internal error) returns False rather than
        raising — a capability we can't confirm is treated as unsupported, never
        assumed supported. Native, non-litellm-routed providers litellm's own
        registry doesn't recognize (e.g. Azure Foundry model names) also fall
        through to False for the same reason.
        """
        if not model_name or not param:
            return False
        try:
            supported = litellm.get_supported_openai_params(model=model_name)
        except Exception as exc:
            logger.warning(
                "llm.supports_param: capability lookup failed for model=%s param=%s: %s",
                model_name,
                param,
                exc,
                extra={"model_name": model_name, "param": param},
            )
            return False
        return bool(supported) and param in supported

    def supports_vision(self, model_name: str) -> bool:
        """Return whether the run's model can accept image (vision) input.

        Backed by litellm's registry (`supports_vision`). Unlike `supports_param`,
        the model id is first routed/prefixed to the provider-qualified form
        litellm recognizes (e.g. ``anthropic/…``, ``gemini/…``; ``bedrock/…`` is
        already prefixed) via the same `_routed_model` the agent model builder
        uses — otherwise non-OpenAI vision models would be mis-detected. Defensive
        by design: any failure (unknown model, litellm error) returns False, so
        images are dropped and the run falls back to OCR text rather than erroring.
        """
        if not model_name:
            return False
        try:
            from llm.services.litellm import LiteLLMAgentModelService

            provider = self._resolve_agent_provider(model_name)
            routed = LiteLLMAgentModelService._routed_model(provider, model_name)
            return bool(litellm.supports_vision(model=routed))
        except Exception as exc:
            logger.warning(
                "llm.supports_vision: capability lookup failed for model=%s: %s",
                model_name,
                exc,
                extra={"model_name": model_name},
            )
            return False

    @staticmethod
    def _build_agent_runtime_kwargs(
        *,
        timeout: int | float | None,
        tracing_disabled: bool | None,
        runtime_kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        kwargs = dict(runtime_kwargs)
        if timeout is not None:
            kwargs.setdefault("timeout", timeout)
        if tracing_disabled is not None:
            kwargs.setdefault("tracing_disabled", tracing_disabled)
        return kwargs

    def list_available_models_for_organization(self, organization_id: str) -> LlmAvailableModelsResponse:
        """Discover available LLM models for an organization via integrations.

        Args:
            organization_id: Organization id.

        Returns:
            LlmAvailableModelsResponse.

        Raises:
            ValidationError: When organization_id is missing.
            ServiceError: When discovery fails or integrations service is not configured.
        """
        if not organization_id:
            raise ValidationError("organization_id is required")
        if self.integrations_service_manager is None:
            raise ServiceError("Integrations service manager is required for model discovery")

        try:
            integrations_response = self.integrations_service_manager.list_organization_integrations(organization_id)
            items = getattr(integrations_response, "items", []) or []
            provider_models: list[LlmProviderModelsResponse] = []

            for item in items:
                capabilities = list(getattr(item, "capabilities", []) or [])
                if "llm" not in capabilities:
                    continue

                provider = str(getattr(item, "provider", "") or "").strip().lower()
                if not provider:
                    continue

                credentials = self.integrations_service_manager.get_provider_credentials(organization_id, provider)
                discovered = self._discover_models_for_integration_provider(provider, credentials)
                if not discovered:
                    continue

                provider_name = str(getattr(item, "label", None) or provider.replace("_", " ").title())
                provider_models.append(
                    LlmProviderModelsResponse(
                        provider=provider,
                        provider_name=provider_name,
                        models=[self._build_model_info(model_id) for model_id in discovered],
                    )
                )

            return LlmAvailableModelsResponse(
                providers=provider_models,
                has_validated_keys=len(provider_models) > 0,
            )
        except ValidationError:
            raise
        except Exception as exc:
            logger.exception(f"llm.list_available_models_for_organization failed org_id={organization_id}: {exc}")
            raise ServiceError(f"Unable to list available llm models: {exc}") from exc

    def list_available_models_for_actor(
        self,
        actor: dict[str, object],
        organization_id: str | None = None,
    ) -> LlmAvailableModelsResponse:
        """List available models for an actor within org scope.

        Args:
            actor: Actor context.
            organization_id: Optional org id; defaults to actor org.

        Returns:
            LlmAvailableModelsResponse.
        """
        actor_organization_id = self._require_actor_field(actor, "organization_id")
        target_organization_id = str(organization_id or actor_organization_id).strip()
        self._authorize_actor_operation(actor, "llm", "read", target_organization_id)
        return self.list_available_models_for_organization(target_organization_id)

    def _discover_models_for_integration_provider(
        self,
        provider: str,
        credentials: dict[str, object],
    ) -> list[str]:
        normalized_provider = str(provider or "").strip().lower()
        discovery_provider_map = {
            "openai": "openai",
            "anthropic": "anthropic",
            "google_gemini": "gemini",
            "azure_openai": "azure",
            "azure_foundry": "azure_foundry",
            "aws_bedrock": "bedrock",
        }
        discovery_provider = discovery_provider_map.get(normalized_provider)
        if discovery_provider is None:
            return []

        discovered = LiteLLMModelDiscoveryService.discover_provider_models(
            discovery_provider,
            credentials=credentials,
            check_provider_endpoint=discovery_provider in {"openai", "anthropic", "gemini"},
        )
        return self._normalize_discovered_models(normalized_provider, discovered)

    def _normalize_discovered_models(self, provider: str, models: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for model in models:
            model_id = str(model or "").strip()
            if not model_id:
                continue
            if provider == "anthropic" and model_id.startswith("anthropic/"):
                model_id = model_id.split("/", 1)[1]
            if provider == "google_gemini":
                if model_id.startswith("gemini/"):
                    model_id = model_id
                elif model_id.startswith("models/"):
                    model_id = f"gemini/{model_id.removeprefix('models/')}"
            if provider == "aws_bedrock" and model_id.startswith("bedrock/"):
                model_id = model_id
            if not self._is_selectable_model(model_id):
                continue
            if model_id in seen:
                continue
            seen.add(model_id)
            normalized.append(model_id)
        return normalized

    def _build_model_info(self, model_id: str) -> LlmModelInfoResponse:
        max_tokens: int | None = None
        input_cost_per_token: float | None = None
        output_cost_per_token: float | None = None

        try:
            info = litellm.get_model_info(model_id)  # type: ignore[union-attr]
            if info:
                max_tokens = getattr(info, "max_output_tokens", None) or getattr(info, "max_tokens", None)
                input_cost_per_token = getattr(info, "input_cost_per_token", None)
                output_cost_per_token = getattr(info, "output_cost_per_token", None)
        except Exception:
            pass

        return LlmModelInfoResponse(
            id=model_id,
            name=self._humanize_model_name(model_id),
            max_tokens=max_tokens,
            input_cost_per_token=input_cost_per_token,
            output_cost_per_token=output_cost_per_token,
        )

    def _authorize_actor_operation(
        self,
        actor: dict[str, object],
        resource: str,
        action: str,
        organization_id: str,
    ) -> None:
        actor_organization_id = self._require_actor_field(actor, "organization_id")
        if organization_id != actor_organization_id:
            raise AuthorizationError("Forbidden organization scope")

    @staticmethod
    def _require_actor_field(actor: dict[str, object], field_name: str) -> str:
        value = actor_str(actor, field_name)
        if not value:
            raise ValidationError(f"actor.{field_name} is required")
        return value

    @staticmethod
    def _is_selectable_model(model_id: str) -> bool:
        try:
            info = litellm.get_model_info(model_id)  # type: ignore[union-attr]
            mode = getattr(info, "mode", None)
            if mode in {"chat", "completion"}:
                return True
            if mode is not None:
                return False
        except Exception:
            pass

        normalized = str(model_id or "").strip().lower()
        blocked_fragments = (
            "embedding",
            "transcribe",
            "tts",
            "speech",
            "audio",
            "realtime",
            "image",
            "moderation",
            "rerank",
            "search",
            "video",
            "omni-moderation",
        )
        return not any(fragment in normalized for fragment in blocked_fragments)

    @staticmethod
    def _humanize_model_name(model_id: str) -> str:
        token = str(model_id or "").strip()
        if "/" in token:
            token = token.split("/", 1)[1]
        token = token.replace("_", " ").replace("-", " ")
        token = re.sub(r"\s+", " ", token).strip()
        return token.title() if token else model_id
