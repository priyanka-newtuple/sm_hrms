"""Amazon Bedrock agent-model service and credential-scoped discovery."""

from __future__ import annotations

import re
from typing import Any

from exceptions import ServiceError
from llm.models.interface import AgentModelBuildContext
from llm.services.bedrock_converse import BedrockConverseModel
from llm.services.openai import OpenAIAgentModelService


def bedrock_mantle_base_url(region: str) -> str:
    """Return the regional OpenAI-compatible Bedrock Mantle endpoint."""
    normalized_region = region.strip()
    if not normalized_region:
        raise ServiceError("Amazon Bedrock region is required")
    return f"https://bedrock-mantle.{normalized_region}.api.aws/v1"


def bedrock_mantle_uses_responses_api(
    model_name: str,
    api_mode: str | None = None,
) -> bool:
    """Choose a Mantle API without assuming every listed model supports Responses.

    Bedrock's OpenAI-shaped Models API only guarantees the model ID, so it
    cannot be used for capability negotiation. Auto mode is deliberately
    conservative: known Responses-capable families use Responses and all
    other models use Chat Completions. The integration override allows newly
    released models to be enabled without a code release.
    """
    normalized_mode = str(api_mode or "auto").strip().lower().replace("-", "_")
    if normalized_mode in {"responses", "response"}:
        return True
    if normalized_mode in {"chat", "chat_completions", "chat_completion"}:
        return False
    if normalized_mode != "auto":
        raise ServiceError(
            "Amazon Bedrock Mantle API must be auto, responses, or chat_completions"
        )

    model_id = model_name.removeprefix("bedrock/").lower()
    if model_id.startswith("openai.gpt-oss-"):
        return "safeguard" not in model_id
    openai_version = re.match(r"^openai\.gpt-(\d+)\.(\d+)(?:-|$)", model_id)
    if openai_version is not None:
        version = (int(openai_version.group(1)), int(openai_version.group(2)))
        return version >= (5, 4)
    return model_id.startswith("xai.grok-4.3")


def _session_kwargs(credentials: dict[str, Any], region: str) -> dict[str, str]:
    values = {
        "aws_access_key_id": credentials.get("aws_access_key_id"),
        "aws_secret_access_key": credentials.get("aws_secret_access_key"),
        "aws_session_token": credentials.get("aws_session_token"),
        "region_name": region,
    }
    return {
        key: str(value).strip()
        for key, value in values.items()
        if value is not None and str(value).strip()
    }


def list_bedrock_model_names(credentials: dict[str, Any]) -> list[str]:
    """List models available through the configured Bedrock transport."""
    region = str(credentials.get("region") or "").strip()
    api_key = str(credentials.get("api_key") or "").strip()
    if not region:
        return []

    if api_key:
        import httpx

        headers = {"Authorization": f"Bearer {api_key}"}
        project = str(credentials.get("project") or "").strip()
        if project:
            headers["OpenAI-Project"] = project
        response = httpx.get(
            f"{bedrock_mantle_base_url(region)}/models",
            headers=headers,
            timeout=20.0,
        )
        response.raise_for_status()
        payload = response.json()
        models = payload.get("data", []) if isinstance(payload, dict) else []
        return [
            str(model.get("id") or "").strip()
            for model in models
            if isinstance(model, dict) and model.get("id")
        ]

    try:
        import boto3
    except ImportError as exc:
        raise ServiceError("boto3 is required for Amazon Bedrock support") from exc

    client = boto3.Session(**_session_kwargs(credentials, region)).client(
        "bedrock", region_name=region
    )
    response = client.list_foundation_models(byOutputModality="TEXT")
    summaries = response.get("modelSummaries", [])
    model_ids = [
        str(summary.get("modelId") or "").strip()
        for summary in summaries
        if isinstance(summary, dict) and summary.get("modelId")
    ]
    try:
        next_token: str | None = None
        while True:
            request = {"nextToken": next_token} if next_token else {}
            profiles = client.list_inference_profiles(**request)
            model_ids.extend(
                str(profile.get("inferenceProfileId") or "").strip()
                for profile in profiles.get("inferenceProfileSummaries", [])
                if isinstance(profile, dict) and profile.get("inferenceProfileId")
            )
            next_token = str(profiles.get("nextToken") or "").strip() or None
            if next_token is None:
                break
    except Exception:
        # Some least-privilege roles can list foundation models but not inference
        # profiles. Keep the useful discovery result in that case.
        pass
    return list(dict.fromkeys(model_ids))


class BedrockAgentModelService(OpenAIAgentModelService):
    """Build tenant-scoped Mantle or native Bedrock model clients."""

    requires_api_key = False

    def build(self, context: AgentModelBuildContext) -> Any:
        region = str(context.credentials.get("region") or "").strip()
        if not region:
            raise ServiceError(
                "Amazon Bedrock region is required under Settings -> Integrations."
            )

        api_key = str(context.api_key or context.credentials.get("api_key") or "").strip()
        if api_key:
            return self._build_mantle_model(context, region, api_key)
        return self._build_native_model(context, region)

    def _build_mantle_model(
        self,
        context: AgentModelBuildContext,
        region: str,
        api_key: str,
    ) -> Any:
        responses_model, chat_model, async_openai = self._sdk_classes()
        client_kwargs = self.agent_client_kwargs(context.runtime_kwargs)
        client_kwargs["base_url"] = bedrock_mantle_base_url(region)
        project = str(context.credentials.get("project") or "").strip()
        if project:
            client_kwargs["project"] = project
        client = async_openai(api_key=api_key, **client_kwargs)
        uses_responses_api = bedrock_mantle_uses_responses_api(
            context.model_name,
            str(context.credentials.get("api_mode") or "auto"),
        )
        return self.finish_openai_model(
            model_name=context.model_name.removeprefix("bedrock/"),
            provider=context.provider.value,
            openai_client=client,
            responses_model_class=responses_model,
            chat_model_class=chat_model,
            uses_responses_api=uses_responses_api,
            runtime_kwargs=context.runtime_kwargs,
        )

    @staticmethod
    def _build_native_model(
        context: AgentModelBuildContext,
        region: str,
    ) -> BedrockConverseModel:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise ServiceError("boto3 is required for Amazon Bedrock support") from exc

        session = boto3.Session(**_session_kwargs(context.credentials, region))
        timeout = context.runtime_kwargs.get("timeout") or 600
        max_retries = context.runtime_kwargs.get("max_retries", 2)
        client = session.client(
            "bedrock-runtime",
            region_name=region,
            config=Config(
                read_timeout=float(timeout),
                retries={"max_attempts": int(max_retries), "mode": "standard"},
            ),
        )
        model = BedrockConverseModel(model=context.model_name, client=client)
        model.runtime_kwargs = context.runtime_kwargs
        return model
