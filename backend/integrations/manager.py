"""Business logic manager for integrations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, cast

import litellm as _litellm

from common.auth import actor_str
from common.enums import ModuleStatus
from exceptions import AuthorizationError, ServiceError, ValidationError

from .models.interface import (
    IntegrationCapability,
    IntegrationDefinitionContract,
    IntegrationFieldDefinitionContract,
    IntegrationStatus,
    OrganizationIntegrationContract,
    get_provider_definition,
    list_provider_definitions,
    normalize_capability,
    normalize_provider,
)
from .models.request import (
    ConnectIntegrationRequest,
    ListCalendarEventsRequest,
    ScheduleCalendarEventRequest,
    SetCapabilityDefaultRequest,
    UpsertOrganizationIntegrationRequest,
    ValidateOrganizationIntegrationRequest,
)
from .models.response import (
    CalendarEventResponse,
    CalendarEventsListResponse,
    CapabilityDefaultResponse,
    CapabilityDefaultsListResponse,
    IntegrationConnectionResponse,
    IntegrationConnectionsListResponse,
    IntegrationDefinitionResponse,
    IntegrationDefinitionsListResponse,
    IntegrationFieldDefinitionResponse,
    IntegrationsCalendarStatusResponse,
    IntegrationValidationResponse,
    OrganizationIntegrationResponse,
    OrganizationIntegrationsListResponse,
)

if TYPE_CHECKING:
    from auth.models.response import AccessCheckResponse
    from database.manager import DatabaseServiceManager
    from integrations.db_models import IntegrationsModelService


class AuthAccessService(Protocol):
    def check_access(self, payload: dict[str, object]) -> AccessCheckResponse:
        """Return an authorization decision for the given payload."""
        ...


class IntegrationsServiceManager:
    """Integration and scheduling orchestration service."""

    def __init__(
        self,
        integrations_db_model_service: IntegrationsModelService,
        database_service_manager: DatabaseServiceManager | None,
        config: object | None,
        auth_service_manager: AuthAccessService | None = None,
        *dependencies: object,
    ) -> None:
        self.integrations_db_model_service = integrations_db_model_service
        self.db_model_service = integrations_db_model_service
        self.model_service = integrations_db_model_service
        self.database_service_manager = database_service_manager
        self.config = config
        self.dependencies = list(dependencies)
        self.module_name = "integrations"
        self._started = False
        self.auth_service_manager = auth_service_manager or self._resolve_identity_service(
            dependencies
        )

    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False

    def get_status(self) -> IntegrationsCalendarStatusResponse:
        return IntegrationsCalendarStatusResponse(
            module=self.module_name,
            status=ModuleStatus.READY.value,
            started=self._started,
        )

    def list_definitions(self) -> IntegrationDefinitionsListResponse:
        return IntegrationDefinitionsListResponse(
            items=[
                self._definition_to_response(definition)
                for definition in list_provider_definitions()
            ]
        )

    def list_organization_integrations(
        self, organization_id: str
    ) -> OrganizationIntegrationsListResponse:
        defaults = self.db_model_service.list_capability_defaults(organization_id)
        rows = self.db_model_service.list_organization_integrations(organization_id)
        return OrganizationIntegrationsListResponse(
            organization_id=organization_id,
            items=[self._organization_integration_to_response(row, defaults) for row in rows],
        )

    def get_organization_integration(
        self, organization_id: str, provider: str
    ) -> OrganizationIntegrationResponse | None:
        normalized_provider = normalize_provider(provider)
        row = self.db_model_service.get_organization_integration(
            organization_id, normalized_provider
        )
        if row is None:
            return None
        defaults = self.db_model_service.list_capability_defaults(organization_id)
        return self._organization_integration_to_response(row, defaults)

    def validate_organization_integration(
        self,
        provider: str,
        request: ValidateOrganizationIntegrationRequest,
    ) -> IntegrationValidationResponse:
        normalized_provider = normalize_provider(provider)
        valid, message = self._validate_provider_payload(
            normalized_provider, request.config, request.secrets
        )
        return IntegrationValidationResponse(
            provider=normalized_provider, valid=valid, message=message
        )

    def upsert_organization_integration(
        self,
        organization_id: str,
        provider: str,
        request: UpsertOrganizationIntegrationRequest,
    ) -> OrganizationIntegrationResponse:
        normalized_provider = normalize_provider(provider)
        # Merge provided secrets over the saved ones so editing an integration
        # without re-entering secret fields keeps the previously stored values
        # (the API only ever exposes masked hints, never the secrets themselves).
        merged_secrets = self._merge_with_saved_secrets(
            organization_id, normalized_provider, request.config, request.secrets
        )
        valid = True
        message = "Validation skipped"
        validation_status = "unknown"
        last_error = None
        last_validated_at = None
        if request.validate_provider:
            valid, message = self._validate_provider_payload(
                normalized_provider, request.config, merged_secrets
            )
            validation_status = "valid" if valid else "invalid"
            last_validated_at = datetime.now(UTC)
            if not valid:
                last_error = message

        record = self.db_model_service.upsert_organization_integration(
            organization_id=organization_id,
            provider=normalized_provider,
            display_name=request.display_name,
            config=request.config,
            secrets=merged_secrets,
            status=IntegrationStatus.CONFIGURED if valid else IntegrationStatus.ERROR,
            validation_status=validation_status,
            last_error=last_error,
            last_validated_at=last_validated_at,
        )

        if request.set_default:
            definition = get_provider_definition(normalized_provider)
            for capability in definition.capabilities:
                self.db_model_service.set_capability_default(
                    organization_id, capability, normalized_provider
                )

        defaults = self.db_model_service.list_capability_defaults(organization_id)
        return self._organization_integration_to_response(record, defaults)

    def delete_organization_integration(self, organization_id: str, provider: str) -> bool:
        return self.db_model_service.delete_organization_integration(organization_id, provider)

    def list_capability_defaults(self, organization_id: str) -> CapabilityDefaultsListResponse:
        defaults = self.db_model_service.list_capability_defaults(organization_id)
        items = [
            CapabilityDefaultResponse(capability=capability, provider=provider)
            for capability, provider in sorted(defaults.items())
        ]
        return CapabilityDefaultsListResponse(organization_id=organization_id, items=items)

    def set_capability_default(
        self,
        organization_id: str,
        capability: str,
        request: SetCapabilityDefaultRequest,
    ) -> CapabilityDefaultResponse:
        normalized_capability = normalize_capability(capability)
        normalized_provider = normalize_provider(request.provider)
        definition = get_provider_definition(normalized_provider)
        if normalized_capability not in definition.capabilities:
            raise ValidationError(
                f"provider {normalized_provider} does not support capability {normalized_capability}"
            )
        persisted = self.db_model_service.set_capability_default(
            organization_id, normalized_capability, normalized_provider
        )
        return CapabilityDefaultResponse(capability=normalized_capability, provider=persisted)

    def get_provider_credentials(self, organization_id: str, provider: str) -> dict[str, Any]:
        normalized_provider = normalize_provider(provider)
        integration = self.db_model_service.get_organization_integration(
            organization_id, normalized_provider
        )
        if integration is None:
            return {}
        payload = dict(integration.config)
        payload.update(
            self.db_model_service.get_decrypted_secrets(organization_id, normalized_provider)
        )
        return payload

    def get_credentials_for_capability(
        self, organization_id: str, capability: str
    ) -> tuple[str | None, dict[str, Any]]:
        return self.db_model_service.get_capability_credentials(organization_id, capability)

    def get_llm_credentials(self, organization_id: str, provider: str) -> dict[str, Any]:
        normalized_provider = normalize_provider(provider)
        definition = get_provider_definition(normalized_provider)
        if IntegrationCapability.LLM not in definition.capabilities:
            return {}
        return self.get_provider_credentials(organization_id, normalized_provider)

    def connect_integration(
        self,
        request: ConnectIntegrationRequest | dict[str, object],
    ) -> IntegrationConnectionResponse:
        try:
            connect = (
                request
                if isinstance(request, ConnectIntegrationRequest)
                else ConnectIntegrationRequest.model_validate(request)
            )
            record = self.db_model_service.upsert_integration(connect)
            return IntegrationConnectionResponse(
                organization_id=record.organization_id,
                user_id=record.user_id,
                provider=record.provider,
                provider_account_id=record.provider_account_id,
                connected=record.connected,
                scopes=list(record.scopes),
            )
        except (ValidationError, AuthorizationError):
            raise
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        except Exception as exc:
            raise ServiceError(f"Unable to connect integration: {exc}") from exc

    def list_integrations(
        self, organization_id: str, user_id: str | None = None
    ) -> list[IntegrationConnectionResponse]:
        rows = self.db_model_service.list_integrations(
            organization_id=organization_id, user_id=user_id
        )
        return [
            IntegrationConnectionResponse(
                organization_id=row.organization_id,
                user_id=row.user_id,
                provider=row.provider,
                provider_account_id=row.provider_account_id,
                connected=row.connected,
                scopes=list(row.scopes),
            )
            for row in rows
        ]

    # TODO(modular-integrations): Move calendar event execution out of integrations.
    # This remains here only as a compatibility path until a dedicated
    # calendar/scheduling execution module takes over event operations.
    def schedule_event(
        self,
        request: ScheduleCalendarEventRequest | dict[str, object],
    ) -> CalendarEventResponse:
        try:
            event_request = (
                request
                if isinstance(request, ScheduleCalendarEventRequest)
                else ScheduleCalendarEventRequest.model_validate(request)
            )

            integration = self.db_model_service.get_integration(
                organization_id=event_request.organization_id,
                user_id=event_request.user_id,
                provider=event_request.provider,
            )
            if integration is None or not integration.connected:
                raise ValidationError("integration not connected for provider")

            record = self.db_model_service.create_event(event_request)
            return CalendarEventResponse(
                event_id=record.event_id,
                organization_id=record.organization_id,
                user_id=record.user_id,
                provider=record.provider,
                title=record.title,
                starts_at=record.starts_at,
                ends_at=record.ends_at,
                attendees=list(record.attendees),
                entity_id=record.entity_id,
            )
        except (ValidationError, AuthorizationError):
            raise
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        except Exception as exc:
            raise ServiceError(f"Unable to schedule event: {exc}") from exc

    # TODO(modular-integrations): Move calendar event reads out of integrations.
    # Integrations should be the configuration/control plane, not the event query plane.
    def list_events(
        self,
        request: ListCalendarEventsRequest | dict[str, object],
    ) -> CalendarEventsListResponse:
        try:
            query = (
                request
                if isinstance(request, ListCalendarEventsRequest)
                else ListCalendarEventsRequest.model_validate(request)
            )
            rows = self.db_model_service.list_events(
                organization_id=query.organization_id,
                provider=query.provider,
                user_id=query.user_id,
            )
            return CalendarEventsListResponse(
                items=[
                    CalendarEventResponse(
                        event_id=row.event_id,
                        organization_id=row.organization_id,
                        user_id=row.user_id,
                        provider=row.provider,
                        title=row.title,
                        starts_at=row.starts_at,
                        ends_at=row.ends_at,
                        attendees=list(row.attendees),
                        entity_id=row.entity_id,
                    )
                    for row in rows
                ]
            )
        except (ValidationError, AuthorizationError):
            raise
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        except Exception as exc:
            raise ServiceError(f"Unable to list events: {exc}") from exc

    def connect_integration_for_actor(
        self,
        actor: dict[str, object],
        request: ConnectIntegrationRequest,
    ) -> IntegrationConnectionResponse:
        actor_user_id = self._require_actor_field(actor, "user_id")
        organization_id = request.organization_id or self._require_actor_field(
            actor, "organization_id"
        )
        self._authorize_actor_operation(actor, "integration", "write", organization_id)
        normalized_request = ConnectIntegrationRequest(
            organization_id=organization_id,
            user_id=actor_user_id,
            provider=request.provider,
            provider_account_id=request.provider_account_id,
            scopes=list(request.scopes),
        )
        return self.connect_integration(normalized_request)

    def list_integrations_for_actor(
        self,
        actor: dict[str, object],
        organization_id: str,
        user_id: str | None = None,
    ) -> IntegrationConnectionsListResponse:
        self._authorize_actor_operation(actor, "integration", "read", organization_id)
        items = self.list_integrations(organization_id=organization_id, user_id=user_id)
        return IntegrationConnectionsListResponse(organization_id=organization_id, items=items)

    def list_organization_integrations_for_actor(
        self,
        actor: dict[str, object],
        organization_id: str,
    ) -> OrganizationIntegrationsListResponse:
        self._authorize_actor_operation(actor, "integration", "read", organization_id)
        return self.list_organization_integrations(organization_id)

    def get_organization_integration_for_actor(
        self,
        actor: dict[str, object],
        organization_id: str,
        provider: str,
    ) -> OrganizationIntegrationResponse | None:
        self._authorize_actor_operation(actor, "integration", "read", organization_id)
        return self.get_organization_integration(organization_id, provider)

    def validate_organization_integration_for_actor(
        self,
        actor: dict[str, object],
        organization_id: str,
        provider: str,
        request: ValidateOrganizationIntegrationRequest,
    ) -> IntegrationValidationResponse:
        self._authorize_actor_operation(actor, "integration", "write", organization_id)
        # Reuse saved secrets for blank fields (target-bound), so validating an
        # edit works without re-entering unchanged credentials — matching save.
        normalized_provider = normalize_provider(provider)
        merged_secrets = self._merge_with_saved_secrets(
            organization_id, normalized_provider, request.config, request.secrets
        )
        return self.validate_organization_integration(
            normalized_provider, request.model_copy(update={"secrets": merged_secrets})
        )

    def authorize_test_email(
        self, actor: dict[str, object], organization_id: str, provider: str
    ) -> str:
        """Authorize the actor and confirm the provider can send email.

        Returns the normalized provider name for the caller to send through.
        """
        self._authorize_actor_operation(actor, "integration", "write", organization_id)
        normalized_provider = normalize_provider(provider)
        definition = get_provider_definition(normalized_provider)
        if IntegrationCapability.COMMUNICATION not in definition.capabilities:
            raise ValidationError(
                f"Provider '{normalized_provider}' does not support sending email"
            )
        return normalized_provider

    # Connection-target fields per provider. Saved secrets are only reused when
    # these are unchanged, so stored credentials can never be sent to a different
    # (possibly attacker-supplied) destination.
    _PROVIDER_TARGET_FIELDS: ClassVar[dict[str, tuple[str, ...]]] = {
        "smtp": ("smtp_host", "smtp_port"),
        "ses": ("region",),
        "azure_communication": ("endpoint",),
        "microsoft_graph_email": ("tenant_id", "client_id"),
    }

    def _merge_with_saved_secrets(
        self,
        organization_id: str,
        provider: str,
        config: dict[str, object] | None,
        secrets: dict[str, object] | None,
    ) -> dict[str, object]:
        """Overlay provided (non-blank) secrets onto the saved ones for a provider.

        Lets an edit that leaves secret fields blank keep the stored credentials —
        but only when the connection target (host/region/endpoint) is unchanged,
        so saved secrets are never forwarded to a different destination.
        """
        provided = {k: v for k, v in (secrets or {}).items() if v not in (None, "")}
        saved_secrets = self.db_model_service.get_decrypted_secrets(organization_id, provider)
        if not saved_secrets:
            return provided

        saved = self.db_model_service.get_organization_integration(organization_id, provider)
        saved_config = dict(saved.config) if saved else {}
        target_fields = self._PROVIDER_TARGET_FIELDS.get(provider, ())
        target_unchanged = all(
            str((config or {}).get(field, "")) == str(saved_config.get(field, ""))
            for field in target_fields
        )
        merged: dict[str, object] = dict(saved_secrets) if target_unchanged else {}
        merged.update(provided)
        return merged

    def merged_secrets_for(
        self,
        organization_id: str,
        provider: str,
        config: dict[str, object] | None,
        secrets: dict[str, object] | None,
    ) -> dict[str, object]:
        """Public wrapper: provided secrets overlaid on the saved ones (target-bound)."""
        return self._merge_with_saved_secrets(
            organization_id, normalize_provider(provider), config, secrets
        )

    def upsert_organization_integration_for_actor(
        self,
        actor: dict[str, object],
        organization_id: str,
        provider: str,
        request: UpsertOrganizationIntegrationRequest,
    ) -> OrganizationIntegrationResponse:
        self._authorize_actor_operation(actor, "integration", "write", organization_id)
        return self.upsert_organization_integration(organization_id, provider, request)

    def delete_organization_integration_for_actor(
        self,
        actor: dict[str, object],
        organization_id: str,
        provider: str,
    ) -> bool:
        self._authorize_actor_operation(actor, "integration", "write", organization_id)
        return self.delete_organization_integration(organization_id, provider)

    def list_capability_defaults_for_actor(
        self,
        actor: dict[str, object],
        organization_id: str,
    ) -> CapabilityDefaultsListResponse:
        self._authorize_actor_operation(actor, "integration", "read", organization_id)
        return self.list_capability_defaults(organization_id)

    def set_capability_default_for_actor(
        self,
        actor: dict[str, object],
        organization_id: str,
        capability: str,
        request: SetCapabilityDefaultRequest,
    ) -> CapabilityDefaultResponse:
        self._authorize_actor_operation(actor, "integration", "write", organization_id)
        return self.set_capability_default(organization_id, capability, request)

    def schedule_event_for_actor(
        self,
        actor: dict[str, object],
        request: ScheduleCalendarEventRequest,
    ) -> CalendarEventResponse:
        # TODO(modular-integrations): Remove this actor adapter when calendar/scheduling
        # execution is extracted from the integrations module.
        actor_user_id = self._require_actor_field(actor, "user_id")
        organization_id = request.organization_id or self._require_actor_field(
            actor, "organization_id"
        )
        self._authorize_actor_operation(actor, "integration", "write", organization_id)
        normalized_request = ScheduleCalendarEventRequest(
            organization_id=organization_id,
            user_id=actor_user_id,
            provider=request.provider,
            title=request.title,
            starts_at=request.starts_at,
            ends_at=request.ends_at,
            attendees=list(request.attendees),
            entity_id=request.entity_id,
        )
        return self.schedule_event(normalized_request)

    def list_events_for_actor(
        self,
        actor: dict[str, object],
        request: ListCalendarEventsRequest,
    ) -> CalendarEventsListResponse:
        # TODO(modular-integrations): Remove this actor adapter when calendar/scheduling
        # execution is extracted from the integrations module.
        organization_id = request.organization_id or self._require_actor_field(
            actor, "organization_id"
        )
        self._authorize_actor_operation(actor, "integration", "read", organization_id)
        normalized_request = ListCalendarEventsRequest(
            organization_id=organization_id,
            provider=request.provider,
            user_id=request.user_id,
        )
        return self.list_events(normalized_request)

    def _validate_provider_payload(
        self,
        provider: str,
        config: dict[str, object],
        secrets: dict[str, object],
    ) -> tuple[bool, str]:
        normalized_provider = normalize_provider(provider)
        definition = get_provider_definition(normalized_provider)
        self._validate_required_fields(definition.config_fields, config, "config")
        self._validate_required_fields(definition.secret_fields, secrets, "secrets")

        if normalized_provider in {"openai", "anthropic", "google_gemini"}:
            return self._validate_llm_provider(normalized_provider, secrets)
        if normalized_provider == "azure_foundry":
            return self._validate_foundry_provider(config, secrets)
        if normalized_provider == "aws_bedrock":
            return self._validate_bedrock_provider(config, secrets)
        if normalized_provider in {"smtp", "ses", "azure_communication"}:
            return self._validate_communication_provider(normalized_provider, config, secrets)
        if normalized_provider in {
            "s3",
            "azure_blob",
            "azure_openai",
        }:
            return True, "Configuration accepted"
        if normalized_provider in {"google_calendar", "google", "outlook", "ics"}:
            return True, "Calendar provider requires provider-specific authorization flow"
        return True, "Configuration accepted"

    @staticmethod
    def _validate_required_fields(
        fields: tuple[IntegrationFieldDefinitionContract, ...],
        payload: dict[str, object],
        namespace: str,
    ) -> None:
        missing = [
            field.label
            for field in fields
            if field.required and payload.get(field.name) in (None, "", [])
        ]
        if missing:
            raise ValidationError(f"Missing required {namespace} fields: {', '.join(missing)}")

    def _validate_llm_provider(self, provider: str, secrets: dict[str, object]) -> tuple[bool, str]:
        """Validate credentials against the provider catalog, not a fixed model."""
        api_key = str(secrets.get("api_key", "")).strip()
        if not api_key:
            raise ValidationError("api_key is required")

        normalized_provider = provider.strip().lower()
        if normalized_provider == "openai":
            return self._validate_openai_key(api_key)

        catalog_providers = {
            "anthropic": "anthropic",
            "google_gemini": "gemini",
        }
        catalog_provider = catalog_providers.get(normalized_provider)
        if catalog_provider is None:
            return False, f"Unknown LLM provider: {provider}"

        try:
            models = _litellm.get_valid_models(
                custom_llm_provider=catalog_provider,
                api_key=api_key,
                check_provider_endpoint=True,
            )
            if not models:
                return False, "Provider returned no available models for this API key"
            return True, f"API key is valid ({len(models)} models available)"
        except getattr(_litellm, "AuthenticationError", Exception):
            return False, "Invalid API key - authentication failed"
        except getattr(_litellm, "RateLimitError", Exception):
            return True, "API key is valid (rate limited)"
        except getattr(_litellm, "APIConnectionError", Exception):
            return False, "Could not connect to API - please try again"
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def _validate_openai_key(api_key: str) -> tuple[bool, str]:
        """Validate an OpenAI key without requiring access to any specific model.

        Uses the model-list endpoint instead of a chat completion so that
        project-scoped keys that lack access to the default validation model
        still validate correctly. Validation is about the key, not a model.
        """
        try:
            from openai import APIConnectionError, AuthenticationError, OpenAI
        except ImportError:
            return True, "Configuration accepted"

        try:
            OpenAI(api_key=api_key).models.list()
            return True, "API key is valid"
        except AuthenticationError:
            return False, "Invalid API key - authentication failed"
        except APIConnectionError:
            return False, "Could not connect to API - please try again"
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def _validate_foundry_provider(
        config: dict[str, object], secrets: dict[str, object]
    ) -> tuple[bool, str]:
        """Validate Foundry credentials through its OpenAI v1 model catalog."""
        endpoint = str(config.get("endpoint") or "").strip()
        api_key = str(secrets.get("api_key") or "").strip()
        try:
            from openai import APIConnectionError, AuthenticationError
            from llm.services.azure_foundry import (
                foundry_project_endpoint,
                list_foundry_model_names,
            )
        except ImportError:
            return True, "Configuration accepted"

        if foundry_project_endpoint(endpoint) is None:
            return False, (
                "Use the Foundry Project endpoint ending in "
                "/api/projects/<project-name>; model operation URLs cannot list deployments."
            )

        try:
            available = len(list_foundry_model_names(endpoint, api_key))
            if not available:
                return False, "Microsoft Foundry returned no deployed models"
            return True, f"API key is valid ({available} deployments available)"
        except AuthenticationError:
            return False, "Invalid API key - authentication failed"
        except APIConnectionError:
            return False, "Could not connect to Microsoft Foundry - check the endpoint"
        except Exception as exc:
            status_code = getattr(exc, "status_code", None) or getattr(
                getattr(exc, "response", None), "status_code", None
            )
            if status_code == 404:
                return False, (
                    "Microsoft Foundry model catalog was not found. Use the Foundry resource "
                    "or project endpoint copied from the Foundry portal."
                )
            return False, str(exc)

    @staticmethod
    def _validate_bedrock_provider(
        config: dict[str, object], secrets: dict[str, object]
    ) -> tuple[bool, str]:
        """Validate Bedrock auth and discover models using its selected transport."""
        region = str(config.get("region") or "").strip()
        api_key = str(secrets.get("api_key") or "").strip()
        access_key_id = str(secrets.get("aws_access_key_id") or "").strip()
        secret_access_key = str(secrets.get("aws_secret_access_key") or "").strip()
        api_mode = str(config.get("api_mode") or "auto").strip().lower().replace("-", "_")
        if api_mode not in {
            "auto",
            "responses",
            "response",
            "chat",
            "chat_completions",
            "chat_completion",
        }:
            return False, "Mantle API Mode must be auto, responses, or chat_completions"
        if bool(access_key_id) != bool(secret_access_key):
            return False, "AWS Access Key ID and AWS Secret Access Key must be provided together"

        credentials = {**config, **secrets}
        try:
            from llm.services.bedrock import list_bedrock_model_names

            available = len(list_bedrock_model_names(credentials))
            auth_method = "API key" if api_key else "AWS credentials"
            if not available:
                return False, f"Amazon Bedrock returned no models for these {auth_method}"
            return True, f"{auth_method} is valid ({available} models available)"
        except Exception as exc:
            status_code = getattr(exc, "status_code", None) or getattr(
                getattr(exc, "response", None), "status_code", None
            )
            if status_code in {401, 403}:
                return False, "Amazon Bedrock authentication failed"
            return False, str(exc)

    @staticmethod
    def _validate_communication_provider(
        provider: str,
        config: dict[str, object],
        secrets: dict[str, object],
    ) -> tuple[bool, str]:
        try:
            from mail.db_models import EmailProvider
            from mail.manager import mail_service
        except Exception:
            return True, "Configuration accepted"

        if provider == "smtp":
            return mail_service.validate_credentials_only(
                provider=EmailProvider.SMTP,
                access_key_id=str(secrets.get("username", "")).strip(),
                secret_access_key=str(secrets.get("password", "")).strip(),
                from_email=str(config.get("from_email", "")).strip(),
                smtp_host=str(config.get("smtp_host", "")).strip(),
                smtp_port=int(str(config.get("smtp_port", 0) or 0)),
                smtp_use_tls=bool(config.get("smtp_use_tls", True)),
            )
        if provider == "azure_communication":
            return mail_service.validate_credentials_only(
                provider=EmailProvider.AZURE_COMMUNICATION,
                access_key_id=None,
                secret_access_key=None,
                from_email=str(config.get("from_email", "")).strip(),
                endpoint=str(config.get("endpoint", "")).strip(),
                connection_string=str(secrets.get("connection_string", "")).strip(),
            )
        return mail_service.validate_credentials_only(
            provider=EmailProvider.SES,
            access_key_id=str(secrets.get("aws_access_key_id", "")).strip(),
            secret_access_key=str(secrets.get("aws_secret_access_key", "")).strip(),
            from_email=str(config.get("from_email", "")).strip(),
            region=str(config.get("region", "")).strip(),
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
            raise AuthorizationError(f"Actor missing required field: {field_name}")
        return value

    @staticmethod
    def _resolve_identity_service(dependencies: tuple[object, ...]) -> AuthAccessService | None:
        for dependency in dependencies:
            if hasattr(dependency, "check_access"):
                return cast("AuthAccessService", dependency)
        return None

    @staticmethod
    def _definition_to_response(
        definition: IntegrationDefinitionContract,
    ) -> IntegrationDefinitionResponse:
        return IntegrationDefinitionResponse(
            provider=definition.provider,
            label=definition.label,
            description=definition.description,
            auth_type=definition.auth_type,
            capabilities=list(definition.capabilities),
            config_fields=[
                IntegrationsServiceManager._field_to_response(field)
                for field in definition.config_fields
            ],
            secret_fields=[
                IntegrationsServiceManager._field_to_response(field)
                for field in definition.secret_fields
            ],
            supports_validate=definition.supports_validate,
            supports_authorize=definition.supports_authorize,
            supports_callback=definition.supports_callback,
        )

    @staticmethod
    def _field_to_response(
        field: IntegrationFieldDefinitionContract,
    ) -> IntegrationFieldDefinitionResponse:
        return IntegrationFieldDefinitionResponse(
            name=field.name,
            label=field.label,
            field_type=field.field_type,
            required=field.required,
            secret=field.secret,
            help_text=field.help_text,
            placeholder=field.placeholder,
        )

    @staticmethod
    def _organization_integration_to_response(
        row: OrganizationIntegrationContract,
        defaults: dict[str, str],
    ) -> OrganizationIntegrationResponse:
        definition = get_provider_definition(row.provider)
        is_default_for = [
            capability for capability, provider in defaults.items() if provider == row.provider
        ]
        return OrganizationIntegrationResponse(
            organization_id=row.organization_id,
            provider=row.provider,
            label=definition.label,
            auth_type=row.auth_type,
            capabilities=list(row.capabilities),
            configured=True,
            status=row.status,
            display_name=row.display_name,
            config=dict(row.config),
            secret_hints=dict(row.secret_hints),
            validation_status=row.validation_status,
            last_validated_at=row.last_validated_at,
            last_error=row.last_error,
            is_default_for=is_default_for,
        )
