"""OpenAI agent-model service."""

from __future__ import annotations

import re
from typing import Any

from exceptions import ServiceError
from llm.models.interface import AgentModelBuildContext
from llm.services.base import AgentModelServiceBase
from llm.services.tracing import json_safe_payload

AGENT_CLIENT_KWARG_NAMES = frozenset(
    {
        "timeout",
        "max_retries",
        "base_url",
        "organization",
        "project",
        "default_headers",
        "default_query",
    }
)


class OpenAIAgentModelService(AgentModelServiceBase):
    def build(self, context: AgentModelBuildContext) -> Any:
        responses_model, chat_model, async_openai = self._sdk_classes()
        client = async_openai(
            api_key=self.required_api_key(context),
            **self.agent_client_kwargs(context.runtime_kwargs),
        )
        return self.finish_openai_model(
            model_name=context.model_name,
            provider=context.provider.value,
            openai_client=client,
            responses_model_class=responses_model,
            chat_model_class=chat_model,
            uses_responses_api=self.uses_responses_api(context.model_name),
            runtime_kwargs=context.runtime_kwargs,
        )

    @staticmethod
    def agent_client_kwargs(runtime_kwargs: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in runtime_kwargs.items()
            if key in AGENT_CLIENT_KWARG_NAMES
        }

    def finish_openai_model(
        self,
        *,
        model_name: str,
        provider: str,
        openai_client: Any,
        responses_model_class: Any,
        chat_model_class: Any,
        uses_responses_api: bool,
        runtime_kwargs: dict[str, Any],
    ) -> Any:
        captured_requests: list[dict[str, Any]] = []
        self._attach_request_capture(
            openai_client,
            captured_requests,
            provider,
            uses_responses_api=uses_responses_api,
        )
        model_class = responses_model_class if uses_responses_api else chat_model_class
        model = model_class(model=model_name, openai_client=openai_client)
        model.captured_llm_requests = captured_requests
        model.resolved_provider = provider
        model.runtime_kwargs = runtime_kwargs
        return model

    def _attach_request_capture(
        self,
        openai_client: Any,
        captured_requests: list[dict[str, Any]],
        provider: str,
        *,
        uses_responses_api: bool,
    ) -> None:
        if uses_responses_api:
            if not hasattr(openai_client, "responses"):
                return
            api = "responses"
            endpoint = openai_client.responses
        else:
            if not (
                hasattr(openai_client, "chat")
                and hasattr(openai_client.chat, "completions")
            ):
                return
            api = "chat.completions"
            endpoint = openai_client.chat.completions

        original_create = endpoint.create

        async def create_with_capture(*args: Any, **kwargs: Any) -> Any:
            _ = args
            captured_requests.append(
                {
                    "api": api,
                    "provider": provider,
                    "body": json_safe_payload(kwargs),
                }
            )
            return await original_create(*args, **kwargs)

        endpoint.create = create_with_capture

    @staticmethod
    def uses_responses_api(model_name: str) -> bool:
        """Route GPT-5.6+ models to Responses while preserving legacy models."""
        model_id = model_name.rsplit("/", 1)[-1].lower()
        version = re.match(r"^gpt-(\d+)\.(\d+)(?:-|$)", model_id)
        if version is None:
            return False
        return (int(version.group(1)), int(version.group(2))) >= (5, 6)

    @staticmethod
    def _sdk_classes() -> tuple[Any, Any, Any]:
        try:
            from agents import OpenAIChatCompletionsModel, OpenAIResponsesModel
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ServiceError(
                "OpenAI Agents SDK is not installed. Install the openai-agents package."
            ) from exc
        return OpenAIResponsesModel, OpenAIChatCompletionsModel, AsyncOpenAI
