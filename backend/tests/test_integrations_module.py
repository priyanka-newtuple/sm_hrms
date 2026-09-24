from __future__ import annotations

from integrations.manager import IntegrationsServiceManager
from integrations.models.request import (
    SetCapabilityDefaultRequest,
    UpsertOrganizationIntegrationRequest,
    ValidateOrganizationIntegrationRequest,
)


class FakeIntegrationsModelService:
    def __init__(self) -> None:
        self.integrations: dict[tuple[str, str], object] = {}
        self.defaults: dict[str, dict[str, str]] = {}

    def list_definitions(self):
        return []

    def list_capability_defaults(self, organization_id: str) -> dict[str, str]:
        return dict(self.defaults.get(organization_id, {}))

    def set_capability_default(self, organization_id: str, capability: str, provider: str) -> str:
        self.defaults.setdefault(organization_id, {})[capability] = provider
        return provider

    def list_organization_integrations(self, organization_id: str):
        return [value for (org_id, _), value in self.integrations.items() if org_id == organization_id]

    def get_organization_integration(self, organization_id: str, provider: str):
        return self.integrations.get((organization_id, provider))

    def upsert_organization_integration(
        self,
        organization_id: str,
        provider: str,
        *,
        display_name: str | None,
        config: dict[str, object],
        secrets: dict[str, object],
        status: str,
        validation_status: str | None,
        last_error: str | None,
        last_validated_at,
    ):
        payload = type(
            "IntegrationRecord",
            (),
            {
                "organization_id": organization_id,
                "provider": provider,
                "auth_type": "api_key",
                "capabilities": ("llm",),
                "display_name": display_name,
                "status": status,
                "config": dict(config),
                "secret_hints": {"api_key": "sk-...1234"} if secrets else {},
                "validation_status": validation_status,
                "last_validated_at": last_validated_at.isoformat() if last_validated_at else None,
                "last_error": last_error,
            },
        )()
        self.integrations[(organization_id, provider)] = payload
        return payload

    def delete_organization_integration(self, organization_id: str, provider: str) -> bool:
        return self.integrations.pop((organization_id, provider), None) is not None

    def get_decrypted_secrets(self, organization_id: str, provider: str) -> dict[str, object]:
        if (organization_id, provider) in self.integrations:
            return {"api_key": "resolved-key"}
        return {}

    def get_capability_credentials(self, organization_id: str, capability: str):
        provider = self.defaults.get(organization_id, {}).get(capability)
        if provider:
            return provider, {"api_key": "resolved-key"}
        return None, {}


def test_unified_integrations_upsert_sets_default() -> None:
    manager = IntegrationsServiceManager(FakeIntegrationsModelService(), None, None, None)
    response = manager.upsert_organization_integration(
        "org-1",
        "openai",
        UpsertOrganizationIntegrationRequest(
            display_name="Primary OpenAI",
            config={},
            secrets={"api_key": "sk-test"},
            validate=False,
            set_default=True,
        ),
    )

    assert response.provider == "openai"
    assert "llm" in response.is_default_for


def test_validate_bedrock_api_key_uses_mantle_model_catalog(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict[str, object]:
            return {"data": [{"id": "openai.gpt-oss-120b"}]}

    def fake_get(url, **kwargs):  # noqa: ANN001, ANN202
        captured.update(url=url, **kwargs)
        return FakeResponse()

    monkeypatch.setattr("httpx.get", fake_get)
    manager = IntegrationsServiceManager(FakeIntegrationsModelService(), None, None, None)
    result = manager.validate_organization_integration(
        "aws_bedrock",
        ValidateOrganizationIntegrationRequest(
            config={"region": "us-east-1", "project": "proj_test"},
            secrets={"api_key": "bedrock-test"},
        ),
    )
    assert result.provider == "aws_bedrock"
    assert result.valid is True
    assert result.message == "API key is valid (1 models available)"
    assert captured["url"] == "https://bedrock-mantle.us-east-1.api.aws/v1/models"
    assert captured["headers"] == {
        "Authorization": "Bearer bedrock-test",
        "OpenAI-Project": "proj_test",
    }


def test_validate_bedrock_rejects_partial_iam_credentials() -> None:
    manager = IntegrationsServiceManager(FakeIntegrationsModelService(), None, None, None)
    result = manager.validate_organization_integration(
        "aws_bedrock",
        ValidateOrganizationIntegrationRequest(
            config={"region": "us-east-1"},
            secrets={"aws_access_key_id": "abc"},
        ),
    )

    assert result.valid is False
    assert "must be provided together" in result.message


def test_validate_bedrock_rejects_unknown_mantle_api_mode() -> None:
    manager = IntegrationsServiceManager(FakeIntegrationsModelService(), None, None, None)
    result = manager.validate_organization_integration(
        "aws_bedrock",
        ValidateOrganizationIntegrationRequest(
            config={"region": "us-east-1", "api_mode": "messages"},
            secrets={"api_key": "bedrock-test"},
        ),
    )

    assert result.valid is False
    assert "auto, responses, or chat_completions" in result.message


def test_foundry_rejects_model_operation_url_for_project_discovery() -> None:
    manager = IntegrationsServiceManager(FakeIntegrationsModelService(), None, None, None)

    definition = next(
        item for item in manager.list_definitions().items if item.provider == "azure_foundry"
    )
    result = manager.validate_organization_integration(
        "azure_foundry",
        ValidateOrganizationIntegrationRequest(
            config={
                "endpoint": (
                    "https://resource.services.ai.azure.com/openai/v1/chat/completions"
                )
            },
            secrets={"api_key": "foundry-test"},
        ),
    )

    assert [field.name for field in definition.config_fields] == ["endpoint"]
    assert [field.name for field in definition.secret_fields] == ["api_key"]
    assert result.valid is False
    assert "/api/projects/<project-name>" in result.message


def test_foundry_project_endpoint_lists_deployments(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict[str, object]:
            return {"value": [{"name": "gpt-5"}]}

    def fake_get(url, **kwargs):  # noqa: ANN001, ANN202
        captured.update(url=url, **kwargs)
        return FakeResponse()

    monkeypatch.setattr("httpx.get", fake_get)
    manager = IntegrationsServiceManager(FakeIntegrationsModelService(), None, None, None)

    result = manager.validate_organization_integration(
        "azure_foundry",
        ValidateOrganizationIntegrationRequest(
            config={
                "endpoint": (
                    "https://resource.services.ai.azure.com/api/projects/recruiting"
                )
            },
            secrets={"api_key": "foundry-test"},
        ),
    )

    assert result.valid is True
    assert captured["url"] == (
        "https://resource.services.ai.azure.com/api/projects/recruiting/deployments"
    )


def test_validate_openai_key_is_model_agnostic(monkeypatch) -> None:
    import sys
    import types

    calls = {"list": 0}

    class FakeModels:
        def list(self):
            calls["list"] += 1
            return ["gpt-4o", "o1-mini"]

    class FakeOpenAI:
        def __init__(self, api_key=None) -> None:  # noqa: ANN001
            self.models = FakeModels()

    class _Err(Exception):
        ...

    fake_openai = types.ModuleType("openai")
    fake_openai.OpenAI = FakeOpenAI
    fake_openai.AuthenticationError = _Err
    fake_openai.APIConnectionError = _Err
    monkeypatch.setitem(sys.modules, "openai", fake_openai)

    manager = IntegrationsServiceManager(FakeIntegrationsModelService(), None, None, None)
    result = manager.validate_organization_integration(
        "openai",
        ValidateOrganizationIntegrationRequest(
            config={},
            secrets={"api_key": "sk-test"},
        ),
    )

    # Validation succeeds via the model-list endpoint, never a fixed-model completion.
    assert result.valid is True
    assert calls["list"] == 1


def test_validate_openai_key_rejects_invalid_key(monkeypatch) -> None:
    import sys
    import types

    class _AuthError(Exception):
        ...

    class FakeOpenAI:
        def __init__(self, api_key=None) -> None:  # noqa: ANN001
            raise _AuthError("bad key")

    fake_openai = types.ModuleType("openai")
    fake_openai.OpenAI = FakeOpenAI
    fake_openai.AuthenticationError = _AuthError
    fake_openai.APIConnectionError = Exception
    monkeypatch.setitem(sys.modules, "openai", fake_openai)

    manager = IntegrationsServiceManager(FakeIntegrationsModelService(), None, None, None)
    result = manager.validate_organization_integration(
        "openai",
        ValidateOrganizationIntegrationRequest(
            config={},
            secrets={"api_key": "sk-bad"},
        ),
    )

    assert result.valid is False
    assert "authentication failed" in result.message


def test_validate_gemini_key_uses_provider_catalog(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_get_valid_models(**kwargs):  # noqa: ANN003, ANN202
        calls.append(kwargs)
        return ["gemini/gemini-2.5-flash", "gemini/gemini-2.5-pro"]

    monkeypatch.setattr("integrations.manager._litellm.get_valid_models", fake_get_valid_models)

    manager = IntegrationsServiceManager(FakeIntegrationsModelService(), None, None, None)
    result = manager.validate_organization_integration(
        "google_gemini",
        ValidateOrganizationIntegrationRequest(
            config={},
            secrets={"api_key": "gemini-test"},
        ),
    )

    assert result.valid is True
    assert calls == [
        {
            "custom_llm_provider": "gemini",
            "api_key": "gemini-test",
            "check_provider_endpoint": True,
        }
    ]


def test_set_capability_default_rejects_invalid_capability_provider_pair() -> None:
    manager = IntegrationsServiceManager(FakeIntegrationsModelService(), None, None, None)
    try:
        manager.set_capability_default(
            "org-1",
            "storage",
            SetCapabilityDefaultRequest(provider="openai"),
        )
    except Exception as exc:  # noqa: BLE001
        assert "does not support capability" in str(exc)
    else:
        raise AssertionError("Expected capability validation failure")
