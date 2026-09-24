from __future__ import annotations

import asyncio
import sys
import types
from typing import Any

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from common.data_model import LLMProvider
from exceptions import ServiceError, ValidationError
from llm.controller import LlmRestController
from llm.manager import DEFAULT_AGENT_CHAT_TIMEOUT, LlmServiceManager
from llm.services.azure_foundry import foundry_openai_base_url
from llm.services.bedrock import bedrock_mantle_uses_responses_api
from llm.services.model_discovery import LiteLLMModelDiscoveryService


class FakeLlmModelService:
    def __init__(
        self,
        *,
        default_model: str = "gpt-4o-mini",
        feature_models: dict[tuple[str, str], str] | None = None,
        api_keys: dict[tuple[str | None, str], str] | None = None,
        providers: dict[str, LLMProvider] | None = None,
    ) -> None:
        self.default_model = default_model
        self.feature_models = feature_models or {}
        self.api_keys = api_keys or {}
        self.providers = providers or {}

    def get_default_model(self) -> str:
        return self.default_model

    def get_model_for_feature(self, organization_id: str, feature: str) -> str | None:
        return self.feature_models.get((organization_id, feature))

    def get_api_key_for_model(self, organization_id: str | None, model: str) -> str | None:
        return self.api_keys.get((organization_id, model)) or self.api_keys.get((None, model))

    def get_provider_for_model(self, model: str) -> LLMProvider:
        return self.providers.get(model, LLMProvider.lite_llm)


class MissingProviderLlmModelService(FakeLlmModelService):
    def get_provider_for_model(self, model: str) -> None:
        _ = model
        return None


class FakeIntegrationsManager:
    def __init__(
        self,
        payloads: dict[tuple[str, str], dict[str, str]] | None = None,
        items_by_org: dict[str, list[object]] | None = None,
    ) -> None:
        self.payloads = payloads or {}
        self.items_by_org = items_by_org or {}

    def get_llm_credentials(self, organization_id: str, provider: str) -> dict[str, str]:
        return self.payloads.get((organization_id, provider), {})

    def get_provider_credentials(self, organization_id: str, provider: str) -> dict[str, str]:
        return self.payloads.get((organization_id, provider), {})

    def list_organization_integrations(self, organization_id: str):
        class _Response:
            def __init__(self, items):
                self.items = items

        return _Response(self.items_by_org.get(organization_id, []))


class FakeAuthDecision:
    def __init__(self, allowed: bool, reason: str | None = None) -> None:
        self.allowed = allowed
        self.reason = reason


class FakeAuthServiceManager:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed

    def check_access(self, _payload):
        return FakeAuthDecision(self.allowed, None if self.allowed else "Forbidden")


def _build_client(manager: LlmServiceManager) -> TestClient:
    manager.start()
    controller = LlmRestController(manager)
    router = APIRouter()
    controller.prepare(router)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_llm_status_endpoint() -> None:
    manager = LlmServiceManager(FakeLlmModelService(), database_service_manager=None, config=None)
    client = _build_client(manager)

    response = client.get("/llm/status")
    assert response.status_code == 200
    assert response.json()["module"] == "llm"
    assert response.json()["started"] is True


def test_resolve_model_for_feature_prefers_org_config() -> None:
    manager = LlmServiceManager(
        FakeLlmModelService(feature_models={("org-1", "playbook_agent"): "claude-sonnet"}),
        database_service_manager=None,
        config=None,
    )
    assert manager.resolve_model_for_feature("org-1", "playbook_agent") == "claude-sonnet"


def test_resolve_model_for_feature_falls_back_to_default() -> None:
    manager = LlmServiceManager(
        FakeLlmModelService(default_model="fallback-model"),
        database_service_manager=None,
        config=None,
    )
    assert manager.resolve_model_for_feature("org-1", "unknown-feature") == "fallback-model"


def test_resolve_runtime_for_feature_reports_metadata() -> None:
    manager = LlmServiceManager(
        FakeLlmModelService(
            feature_models={("org-1", "playbook_agent"): "gpt-4o"},
            api_keys={("org-1", "gpt-4o"): "secret-key"},
            providers={"gpt-4o": LLMProvider.openai},
        ),
        database_service_manager=None,
        config=None,
    )

    runtime = manager.resolve_runtime_for_feature("org-1", "playbook_agent")
    assert runtime.model == "gpt-4o"
    assert runtime.provider == LLMProvider.openai.value
    assert runtime.api_key_found is True
    assert runtime.used_fallback is False


@pytest.mark.parametrize(
    ("model_name", "expected_model_api"),
    [
        ("gpt-4o", "chat.completions"),
        ("gpt-5.6-sol", "responses"),
    ],
)
def test_build_agent_chat_model_routes_by_model_capability(
    monkeypatch,
    model_name: str,
    expected_model_api: str,
) -> None:
    captured: dict[str, object] = {}

    async def fake_create(**_kwargs) -> dict[str, object]:
        return {}

    class FakeAsyncOpenAI:
        def __init__(self, api_key=None, **kwargs) -> None:
            captured["api_key"] = api_key
            captured["client_kwargs"] = kwargs
            self.responses = types.SimpleNamespace(create=fake_create)
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(create=fake_create)
            )

    class FakeOpenAIResponsesModel:
        api = "responses"

        def __init__(self, model=None, openai_client=None) -> None:
            self.model = model
            self.openai_client = openai_client

    class FakeOpenAIChatCompletionsModel:
        api = "chat.completions"

        def __init__(self, model=None, openai_client=None) -> None:
            self.model = model
            self.openai_client = openai_client

    fake_agents = types.ModuleType("agents")
    fake_agents.OpenAIResponsesModel = FakeOpenAIResponsesModel
    fake_agents.OpenAIChatCompletionsModel = FakeOpenAIChatCompletionsModel
    fake_openai = types.ModuleType("openai")
    fake_openai.AsyncOpenAI = FakeAsyncOpenAI
    fake_openai.NotGiven = type("NotGiven", (), {})
    monkeypatch.setitem(sys.modules, "agents", fake_agents)
    monkeypatch.setitem(sys.modules, "openai", fake_openai)

    manager = LlmServiceManager(
        FakeLlmModelService(
            api_keys={("org-1", model_name): "org-key"},
            providers={model_name: LLMProvider.openai},
        ),
        database_service_manager=None,
        config=None,
    )

    model = manager.build_agent_chat_model(
        organization_id="org-1",
        model_name=model_name,
    )

    assert model.model == model_name
    assert model.api == expected_model_api
    assert captured["api_key"] == "org-key"
    assert captured["client_kwargs"] == {"timeout": DEFAULT_AGENT_CHAT_TIMEOUT}
    assert model.resolved_provider == LLMProvider.openai.value
    assert model.runtime_kwargs == {"timeout": DEFAULT_AGENT_CHAT_TIMEOUT}
    request_body: dict[str, Any] = {
        "model": model_name,
        "tools": [{"type": "function", "name": "lookup"}],
    }
    if expected_model_api == "responses":
        request_body.update(
            input="Use a tool",
            reasoning={"effort": "medium"},
        )
        create = model.openai_client.responses.create
    else:
        request_body["messages"] = [{"role": "user", "content": "Use a tool"}]
        create = model.openai_client.chat.completions.create
    asyncio.run(create(**request_body))
    assert model.captured_llm_requests == [
        {
            "api": expected_model_api,
            "provider": LLMProvider.openai.value,
            "body": request_body,
        }
    ]


def test_build_agent_chat_model_requires_model_name() -> None:
    manager = LlmServiceManager(FakeLlmModelService(), database_service_manager=None, config=None)

    with pytest.raises(ValidationError, match="model_name is required"):
        manager.build_agent_chat_model(organization_id="org-1", model_name="")


def test_build_agent_chat_model_delegates_to_registered_provider_service() -> None:
    captured: dict[str, Any] = {}
    sentinel = object()

    class CountingModelService(FakeLlmModelService):
        provider_lookups = 0

        def get_provider_for_model(self, model: str) -> LLMProvider:
            self.provider_lookups += 1
            return super().get_provider_for_model(model)

    class FakeAgentModelService:
        requires_api_key = False

        @staticmethod
        def build(context) -> object:
            captured["context"] = context
            return sentinel

    model_service = CountingModelService(
        providers={"gpt-4o": LLMProvider.openai}
    )
    manager = LlmServiceManager(model_service)
    manager.agent_model_services = {
        LLMProvider.openai: FakeAgentModelService(),
    }

    result = manager.build_agent_chat_model(
        organization_id="org-1",
        model_name="gpt-4o",
    )

    assert result is sentinel
    assert captured["context"].provider == LLMProvider.openai
    assert captured["context"].model_name == "gpt-4o"
    assert captured["context"].runtime_kwargs == {
        "timeout": DEFAULT_AGENT_CHAT_TIMEOUT
    }
    assert model_service.provider_lookups == 1


def test_build_agent_chat_model_reports_missing_sdk(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "agents", None)
    manager = LlmServiceManager(FakeLlmModelService(), database_service_manager=None, config=None)

    with pytest.raises(ServiceError, match="OpenAI Agents SDK is not installed"):
        manager.build_agent_chat_model(organization_id="org-1", model_name="gpt-4o")


def test_build_agent_chat_model_rejects_missing_provider(monkeypatch) -> None:
    fake_agents = types.ModuleType("agents")
    fake_agents.OpenAIResponsesModel = object
    fake_agents.OpenAIChatCompletionsModel = object
    fake_openai = types.ModuleType("openai")
    fake_openai.AsyncOpenAI = object
    monkeypatch.setitem(sys.modules, "agents", fake_agents)
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    manager = LlmServiceManager(
        MissingProviderLlmModelService(api_keys={("org-1", "gpt-4o"): "org-key"}),
        database_service_manager=None,
        config=None,
    )

    with pytest.raises(ServiceError, match="Unable to resolve llm provider"):
        manager.build_agent_chat_model(organization_id="org-1", model_name="gpt-4o")


@pytest.mark.parametrize(
    "deployment",
    [
        "grok-4-20-reasoning",
        "gpt-5",
        "gpt-5.6-sol",
    ],
)
def test_build_agent_model_uses_unified_foundry_responses_api(
    monkeypatch,
    deployment: str,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_create(**_kwargs) -> dict[str, object]:
        return {}

    class FakeAsyncOpenAI:
        def __init__(self, api_key=None, **kwargs) -> None:
            captured["api_key"] = api_key
            captured["client_kwargs"] = kwargs
            self.responses = types.SimpleNamespace(create=fake_create)
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(create=fake_create)
            )

    class FakeResponsesModel:
        api = "responses"

        def __init__(self, model=None, openai_client=None) -> None:
            self.model = model
            self.openai_client = openai_client

    class FakeChatModel:
        api = "chat.completions"

        def __init__(self, model=None, openai_client=None) -> None:
            self.model = model
            self.openai_client = openai_client

    fake_agents = types.ModuleType("agents")
    fake_agents.OpenAIResponsesModel = FakeResponsesModel
    fake_agents.OpenAIChatCompletionsModel = FakeChatModel
    fake_openai = types.ModuleType("openai")
    fake_openai.AsyncOpenAI = FakeAsyncOpenAI
    fake_openai.NotGiven = type("NotGiven", (), {})
    monkeypatch.setitem(sys.modules, "agents", fake_agents)
    monkeypatch.setitem(sys.modules, "openai", fake_openai)

    model_name = f"foundry/{deployment}"
    manager = LlmServiceManager(
        FakeLlmModelService(
            providers={model_name: LLMProvider.azure_foundry},
        ),
        integrations_service_manager=FakeIntegrationsManager(
            {
                ("org-1", "azure_foundry"): {
                    "api_key": "foundry-key",
                    "endpoint": (
                        "https://tenant.services.ai.azure.com/api/projects/recruiting"
                    ),
                }
            }
        ),
    )

    model = manager.build_agent_chat_model(
        organization_id="org-1",
        model_name=model_name,
    )

    assert model.model == deployment
    assert model.api == "responses"
    assert model.resolved_provider == LLMProvider.azure_foundry.value
    assert captured["api_key"] == "foundry-key"
    assert captured["client_kwargs"]["base_url"] == (
        "https://tenant.services.ai.azure.com/openai/v1/"
    )


def test_build_agent_model_uses_tenant_scoped_bedrock_client(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class FakeBedrockClient:
        def converse(self, **_kwargs):
            return {"output": {"message": {"content": []}}, "usage": {}}

    class FakeSession:
        def __init__(self, **kwargs) -> None:
            captured["session_kwargs"] = kwargs

        def client(self, service_name, **kwargs):
            captured["service_name"] = service_name
            captured["client_kwargs"] = kwargs
            return FakeBedrockClient()

    import boto3

    monkeypatch.setattr(boto3, "Session", FakeSession)
    model_name = "bedrock/us.anthropic.claude-sonnet-4-6"
    manager = LlmServiceManager(
        FakeLlmModelService(providers={model_name: LLMProvider.bedrock}),
        integrations_service_manager=FakeIntegrationsManager(
            {
                ("org-1", "aws_bedrock"): {
                    "region": "us-east-1",
                    "aws_access_key_id": "tenant-access-key",
                    "aws_secret_access_key": "tenant-secret-key",
                    "aws_session_token": "tenant-session-token",
                }
            }
        ),
    )

    model = manager.build_agent_chat_model(
        organization_id="org-1",
        model_name=model_name,
    )

    assert model.model == "us.anthropic.claude-sonnet-4-6"
    assert model.resolved_provider == LLMProvider.bedrock.value
    assert captured["session_kwargs"] == {
        "aws_access_key_id": "tenant-access-key",
        "aws_secret_access_key": "tenant-secret-key",
        "aws_session_token": "tenant-session-token",
        "region_name": "us-east-1",
    }
    assert captured["service_name"] == "bedrock-runtime"
    assert captured["client_kwargs"]["region_name"] == "us-east-1"


@pytest.mark.parametrize(
    ("model_name", "expected_api"),
    [
        ("bedrock/openai.gpt-oss-120b", "responses"),
        ("bedrock/openai.gpt-5.6-sol", "responses"),
        ("bedrock/deepseek.v3.2", "chat.completions"),
    ],
)
def test_build_agent_model_uses_supported_bedrock_mantle_api(
    monkeypatch,
    model_name: str,
    expected_api: str,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_create(**_kwargs) -> dict[str, object]:
        return {}

    class FakeAsyncOpenAI:
        def __init__(self, api_key=None, **kwargs) -> None:
            captured["api_key"] = api_key
            captured["client_kwargs"] = kwargs
            self.responses = types.SimpleNamespace(create=fake_create)
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(create=fake_create)
            )

    class FakeResponsesModel:
        api = "responses"

        def __init__(self, model=None, openai_client=None) -> None:
            self.model = model
            self.openai_client = openai_client

    class FakeChatModel:
        api = "chat.completions"

        def __init__(self, model=None, openai_client=None) -> None:
            self.model = model
            self.openai_client = openai_client

    fake_agents = types.ModuleType("agents")
    fake_agents.OpenAIResponsesModel = FakeResponsesModel
    fake_agents.OpenAIChatCompletionsModel = FakeChatModel
    fake_openai = types.ModuleType("openai")
    fake_openai.AsyncOpenAI = FakeAsyncOpenAI
    fake_openai.NotGiven = type("NotGiven", (), {})
    monkeypatch.setitem(sys.modules, "agents", fake_agents)
    monkeypatch.setitem(sys.modules, "openai", fake_openai)

    manager = LlmServiceManager(
        FakeLlmModelService(providers={model_name: LLMProvider.bedrock}),
        integrations_service_manager=FakeIntegrationsManager(
            {
                ("org-1", "aws_bedrock"): {
                    "region": "us-east-1",
                    "project": "proj_recruiting",
                    "api_key": "tenant-bedrock-key",
                }
            }
        ),
    )

    model = manager.build_agent_chat_model(
        organization_id="org-1",
        model_name=model_name,
    )

    assert model.model == model_name.removeprefix("bedrock/")
    assert model.api == expected_api
    assert model.resolved_provider == LLMProvider.bedrock.value
    assert captured["api_key"] == "tenant-bedrock-key"
    assert captured["client_kwargs"]["base_url"] == (
        "https://bedrock-mantle.us-east-1.api.aws/v1"
    )
    assert captured["client_kwargs"]["project"] == "proj_recruiting"


def test_bedrock_mantle_api_mode_override_supports_new_models() -> None:
    assert bedrock_mantle_uses_responses_api(
        "bedrock/provider.future-model",
        "responses",
    ) is True
    assert bedrock_mantle_uses_responses_api(
        "bedrock/openai.gpt-5.6-sol",
        "chat_completions",
    ) is False


def test_bedrock_api_key_discovery_uses_mantle_models(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict[str, object]:
            return {
                "data": [
                    {"id": "openai.gpt-oss-120b"},
                    {"id": "anthropic.claude-sonnet-4-6"},
                ]
            }

    def fake_get(url, **kwargs):  # noqa: ANN001, ANN202
        captured.update(url=url, **kwargs)
        return FakeResponse()

    monkeypatch.setattr("httpx.get", fake_get)

    discovered = LiteLLMModelDiscoveryService.discover_provider_models(
        "bedrock",
        credentials={
            "region": "us-west-2",
            "api_key": "bedrock-key",
        },
    )

    assert discovered == [
        "bedrock/openai.gpt-oss-120b",
        "bedrock/anthropic.claude-sonnet-4-6",
    ]
    assert captured["url"] == "https://bedrock-mantle.us-west-2.api.aws/v1/models"


def test_bedrock_iam_discovery_includes_inference_profiles(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeBedrockControlClient:
        @staticmethod
        def list_foundation_models(**kwargs):  # noqa: ANN003, ANN202
            captured["foundation_kwargs"] = kwargs
            return {"modelSummaries": [{"modelId": "amazon.nova-pro-v1:0"}]}

        @staticmethod
        def list_inference_profiles(**kwargs):  # noqa: ANN003, ANN202
            captured["profile_kwargs"] = kwargs
            return {
                "inferenceProfileSummaries": [
                    {"inferenceProfileId": "us.anthropic.claude-sonnet-4-6"}
                ]
            }

    class FakeSession:
        def __init__(self, **kwargs) -> None:
            captured["session_kwargs"] = kwargs

        def client(self, service_name, **kwargs):
            captured["service_name"] = service_name
            captured["client_kwargs"] = kwargs
            return FakeBedrockControlClient()

    import boto3

    monkeypatch.setattr(boto3, "Session", FakeSession)
    discovered = LiteLLMModelDiscoveryService.discover_provider_models(
        "bedrock",
        credentials={
            "region": "us-east-1",
            "aws_access_key_id": "tenant-key",
            "aws_secret_access_key": "tenant-secret",
        },
    )

    assert discovered == [
        "bedrock/amazon.nova-pro-v1:0",
        "bedrock/us.anthropic.claude-sonnet-4-6",
    ]
    assert captured["service_name"] == "bedrock"
    assert captured["foundation_kwargs"] == {"byOutputModality": "TEXT"}


@pytest.mark.parametrize(
    ("provider", "integration_provider", "model_name", "routed_model"),
    [
        (
            LLMProvider.anthropic_ai,
            "anthropic",
            "claude-sonnet-4-6",
            "anthropic/claude-sonnet-4-6",
        ),
        (
            LLMProvider.gemini_ai,
            "google_gemini",
            "gemini-2.5-pro",
            "gemini/gemini-2.5-pro",
        ),
    ],
)
def test_build_agent_model_keeps_litellm_routes_for_anthropic_and_gemini(
    provider: LLMProvider,
    integration_provider: str,
    model_name: str,
    routed_model: str,
) -> None:
    manager = LlmServiceManager(
        FakeLlmModelService(providers={model_name: provider}),
        integrations_service_manager=FakeIntegrationsManager(
            {("org-1", integration_provider): {"api_key": "tenant-key"}}
        ),
    )

    model = manager.build_agent_chat_model(
        organization_id="org-1",
        model_name=model_name,
    )

    assert model.model == routed_model
    assert model.api_key == "tenant-key"
    assert model.resolved_provider == provider.value
    assert model.runtime_kwargs == {"timeout": DEFAULT_AGENT_CHAT_TIMEOUT}


def test_list_available_models_prefers_provider_discovery() -> None:
    original = LlmServiceManager._discover_models_for_integration_provider
    LlmServiceManager._discover_models_for_integration_provider = (
        lambda self, provider, credentials: ["gpt-4o-mini", "gpt-4.1"] if provider == "openai" else []
    )
    try:
        integration = type(
            "Integration",
            (),
            {
                "provider": "openai",
                "label": "OpenAI",
                "capabilities": ["llm"],
            },
        )()
        manager = LlmServiceManager(
            FakeLlmModelService(),
            database_service_manager=None,
            config=None,
            integrations_service_manager=FakeIntegrationsManager(
                payloads={("org-1", "openai"): {"api_key": "sk-test"}},
                items_by_org={"org-1": [integration]},
            ),
        )
        response = manager.list_available_models_for_organization("org-1")
        assert response.has_validated_keys is True
        assert len(response.providers) == 1
        assert response.providers[0].provider == "openai"
        assert [model.id for model in response.providers[0].models] == ["gpt-4o-mini", "gpt-4.1"]
    finally:
        LlmServiceManager._discover_models_for_integration_provider = original


def test_azure_discovery_uses_configured_deployment() -> None:
    assert LiteLLMModelDiscoveryService.discover_provider_models(
        "azure",
        credentials={"deployment_name": "recruiting-agent"},
    ) == ["azure/recruiting-agent"]


def test_foundry_discovery_does_not_fall_back_to_model_catalog() -> None:
    assert LiteLLMModelDiscoveryService.discover_provider_models(
        "azure_foundry",
        credentials={
            "endpoint": "https://resource.services.ai.azure.com",
            "api_key": "foundry-key",
        },
    ) == []


def test_foundry_discovery_uses_project_deployment_names(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict[str, object]:
            return {
                "value": [
                    {"name": "text-embedding-3-small"},
                    {"name": "gpt-5", "modelName": "gpt-5-2025-08-07"},
                ]
            }

    def fake_get(url, **kwargs):  # noqa: ANN001, ANN202
        captured.update(url=url, **kwargs)
        return FakeResponse()

    monkeypatch.setattr("httpx.get", fake_get)

    discovered = LiteLLMModelDiscoveryService.discover_provider_models(
        "azure_foundry",
        credentials={
            "endpoint": (
                "https://resource.services.ai.azure.com/api/projects/recruiting"
            ),
            "api_key": "foundry-key",
        },
    )

    assert discovered == [
        "foundry/text-embedding-3-small",
        "foundry/gpt-5",
    ]
    assert captured["url"] == (
        "https://resource.services.ai.azure.com/api/projects/recruiting/deployments"
    )


def test_foundry_base_url_accepts_full_responses_operation_url() -> None:
    assert foundry_openai_base_url(
        "https://resource.services.ai.azure.com/openai/v1/responses"
    ) == "https://resource.services.ai.azure.com/openai/v1/"


def test_llm_models_endpoint_returns_provider_groups() -> None:
    original = LlmServiceManager._discover_models_for_integration_provider
    LlmServiceManager._discover_models_for_integration_provider = (
        lambda self, provider, credentials: ["gpt-4o-mini"] if provider == "openai" else []
    )
    try:
        integration = type(
            "Integration",
            (),
            {
                "provider": "openai",
                "label": "OpenAI",
                "capabilities": ["llm"],
            },
        )()
        manager = LlmServiceManager(
            FakeLlmModelService(),
            database_service_manager=None,
            config=None,
            integrations_service_manager=FakeIntegrationsManager(
                payloads={("org-1", "openai"): {"api_key": "sk-test"}},
                items_by_org={"org-1": [integration]},
            ),
        )
        client = _build_client(manager)
        response = client.get(
            "/llm/models",
            params={"organization_id": "org-1"},
            headers={"x-user-id": "user-1", "x-org-id": "org-1", "x-user-roles": "admin"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["has_validated_keys"] is True
        assert body["providers"][0]["provider"] == "openai"
        assert body["providers"][0]["models"][0]["id"] == "gpt-4o-mini"
    finally:
        LlmServiceManager._discover_models_for_integration_provider = original


def test_llm_models_endpoint_defaults_to_actor_org_scope() -> None:
    original = LlmServiceManager._discover_models_for_integration_provider
    LlmServiceManager._discover_models_for_integration_provider = (
        lambda self, provider, credentials: ["gpt-4o-mini"] if provider == "openai" else []
    )
    try:
        integration = type(
            "Integration",
            (),
            {
                "provider": "openai",
                "label": "OpenAI",
                "capabilities": ["llm"],
            },
        )()
        manager = LlmServiceManager(
            FakeLlmModelService(),
            database_service_manager=None,
            config=None,
            integrations_service_manager=FakeIntegrationsManager(
                payloads={("actor-org", "openai"): {"api_key": "sk-test"}},
                items_by_org={"actor-org": [integration]},
            ),
        )
        client = _build_client(manager)
        response = client.get("/llm/models", headers={"x-user-id": "user-1", "x-org-id": "actor-org", "x-user-roles": "admin"})
        assert response.status_code == 200
        assert response.json()["providers"][0]["provider"] == "openai"
    finally:
        LlmServiceManager._discover_models_for_integration_provider = original


def test_llm_models_endpoint_rejects_cross_org_without_authz() -> None:
    manager = LlmServiceManager(
        FakeLlmModelService(),
        database_service_manager=None,
        config=None,
        auth_service_manager=FakeAuthServiceManager(allowed=False),
        integrations_service_manager=FakeIntegrationsManager(),
    )
    client = _build_client(manager)
    response = client.get(
        "/llm/models",
        params={"organization_id": "other-org"},
        headers={"x-user-id": "user-1", "x-org-id": "actor-org", "x-user-roles": "admin"},
    )
    assert response.status_code == 403
