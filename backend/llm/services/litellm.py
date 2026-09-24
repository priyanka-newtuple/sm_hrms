"""LiteLLM-backed agent-model service."""

from __future__ import annotations

from typing import Any

from common.data_model import LLMProvider
from exceptions import ServiceError
from llm.models.interface import AgentModelBuildContext
from llm.services.base import AgentModelServiceBase
from llm.services.tracing import json_safe_payload


class LiteLLMAgentModelService(AgentModelServiceBase):
    def build(self, context: AgentModelBuildContext) -> Any:
        try:
            from agents.extensions.models.litellm_model import LitellmModel
        except ImportError as exc:
            raise ServiceError(
                "LiteLLM support for the OpenAI Agents SDK is not installed."
            ) from exc

        routed_model = self._routed_model(context.provider, context.model_name)
        model = LitellmModel(
            model=routed_model,
            api_key=self.required_api_key(context),
            base_url=str(context.credentials.get("endpoint") or "").strip() or None,
        )
        model.captured_llm_requests = []
        model.resolved_provider = context.provider.value
        model.runtime_kwargs = context.runtime_kwargs
        self._attach_request_capture(model, routed_model, context.provider.value)
        return model

    @staticmethod
    def _routed_model(provider: LLMProvider, model_name: str) -> str:
        if provider == LLMProvider.anthropic_ai and not model_name.startswith("anthropic/"):
            return f"anthropic/{model_name}"
        if provider == LLMProvider.gemini_ai and not model_name.startswith(
            ("gemini/", "vertex_ai/")
        ):
            return f"gemini/{model_name}"
        return model_name

    def _attach_request_capture(self, model: Any, model_name: str, provider: str) -> None:
        original_get_response = model.get_response

        async def get_response_with_capture(*args: Any, **kwargs: Any) -> Any:
            input_value = kwargs.get("input")
            if input_value is None and len(args) > 1:
                input_value = args[1]
            tools = kwargs.get("tools")
            if tools is None and len(args) > 3:
                tools = args[3]
            model.captured_llm_requests.append(
                {
                    "api": "litellm.completion",
                    "provider": provider,
                    "body": json_safe_payload(
                        {"model": model_name, "input": input_value, "tools": tools or []}
                    ),
                }
            )
            return await original_get_response(*args, **kwargs)

        model.get_response = get_response_with_capture
