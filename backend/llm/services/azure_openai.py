"""Legacy Azure OpenAI agent-model service."""

from __future__ import annotations

from typing import Any

from exceptions import ServiceError
from llm.models.interface import AgentModelBuildContext
from llm.services.openai import OpenAIAgentModelService


class AzureOpenAIAgentModelService(OpenAIAgentModelService):
    def build(self, context: AgentModelBuildContext) -> Any:
        try:
            from agents import OpenAIChatCompletionsModel, OpenAIResponsesModel
            from openai import AsyncAzureOpenAI
        except ImportError as exc:
            raise ServiceError(
                "OpenAI Agents SDK is not installed. Install the openai-agents package."
            ) from exc

        endpoint = str(context.credentials.get("endpoint") or "").strip()
        api_version = str(context.credentials.get("api_version") or "").strip()
        deployment = str(context.credentials.get("deployment_name") or "").strip()
        if not all((context.api_key, endpoint, api_version, deployment)):
            raise ServiceError(
                "Azure OpenAI requires endpoint, api_version, deployment_name, and api_key."
            )
        selected_deployment = context.model_name.removeprefix("azure/") or deployment
        client_kwargs = self.agent_client_kwargs(context.runtime_kwargs)
        client_kwargs.pop("base_url", None)
        client = AsyncAzureOpenAI(
            api_key=context.api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
            azure_deployment=selected_deployment,
            **client_kwargs,
        )
        return self.finish_openai_model(
            model_name=selected_deployment,
            provider=context.provider.value,
            openai_client=client,
            responses_model_class=OpenAIResponsesModel,
            chat_model_class=OpenAIChatCompletionsModel,
            uses_responses_api=False,
            runtime_kwargs=context.runtime_kwargs,
        )
