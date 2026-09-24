"""Microsoft Foundry agent-model service."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

from exceptions import ServiceError
from llm.models.interface import AgentModelBuildContext
from llm.services.openai import OpenAIAgentModelService


def foundry_openai_base_url(endpoint: str) -> str:
    """Return the resource-level OpenAI v1 URL for a Foundry endpoint.

    Foundry's UI commonly exposes a project endpoint ending in
    ``/api/projects/<project>``. API-key based model inference uses the
    account resource origin instead of that project path.
    """
    normalized = endpoint.strip().rstrip("/")
    parsed = urlsplit(normalized)
    if "/api/projects/" in parsed.path:
        normalized = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    else:
        openai_v1_index = parsed.path.lower().find("/openai/v1")
        if openai_v1_index >= 0:
            normalized = urlunsplit(
                (
                    parsed.scheme,
                    parsed.netloc,
                    parsed.path[: openai_v1_index + len("/openai/v1")],
                    "",
                    "",
                )
            )
    if normalized.endswith("/openai/v1"):
        return f"{normalized}/"
    return f"{normalized}/openai/v1/"


def foundry_project_endpoint(endpoint: str) -> str | None:
    """Return the canonical project endpoint when one was supplied."""
    normalized = endpoint.strip().rstrip("/")
    parsed = urlsplit(normalized)
    marker = "/api/projects/"
    marker_index = parsed.path.find(marker)
    if marker_index < 0:
        return None
    project_path = parsed.path[marker_index + len(marker) :].split("/", 1)[0]
    if not project_path:
        return None
    path = f"{parsed.path[:marker_index]}{marker}{project_path}"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def list_foundry_model_names(endpoint: str, api_key: str) -> list[str]:
    """List model deployment names from a Foundry project endpoint."""
    project_endpoint = foundry_project_endpoint(endpoint)
    if project_endpoint is None:
        return []

    import httpx

    response = httpx.get(
        f"{project_endpoint}/deployments",
        params={"api-version": "v1"},
        headers={"api-key": api_key},
        timeout=20.0,
    )
    response.raise_for_status()
    payload = response.json()
    deployments = payload.get("value", []) if isinstance(payload, dict) else []
    return [
        str(deployment.get("name") or "").strip()
        for deployment in deployments
        if isinstance(deployment, dict) and deployment.get("name")
    ]


class AzureFoundryAgentModelService(OpenAIAgentModelService):
    def build(self, context: AgentModelBuildContext) -> Any:
        responses_model, chat_model, async_openai = self._sdk_classes()
        endpoint = str(context.credentials.get("endpoint") or "").strip()
        deployment = str(context.credentials.get("deployment_name") or "").strip()
        if not endpoint or not context.api_key:
            raise ServiceError(
                "Microsoft Foundry requires an endpoint and API key under Settings -> Integrations."
            )
        selected_deployment = (
            context.model_name.split("/", 1)[1]
            if "/" in context.model_name
            else deployment
        )
        if not selected_deployment:
            raise ServiceError("Select a Microsoft Foundry model for this agent")

        client_kwargs = self.agent_client_kwargs(context.runtime_kwargs)
        client_kwargs["base_url"] = self._openai_base_url(endpoint)
        client = async_openai(api_key=context.api_key, **client_kwargs)
        return self.finish_openai_model(
            model_name=selected_deployment,
            provider=context.provider.value,
            openai_client=client,
            responses_model_class=responses_model,
            chat_model_class=chat_model,
            # Foundry's OpenAI v1 Responses API is the unified interface for
            # project deployments, including models that also advertise a
            # native Chat Completions endpoint in the portal.
            uses_responses_api=True,
            runtime_kwargs=context.runtime_kwargs,
        )

    @staticmethod
    def _openai_base_url(endpoint: str) -> str:
        return foundry_openai_base_url(endpoint)
