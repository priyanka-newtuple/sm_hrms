"""Interface models and contracts for integrations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import ConfigDict, Field

from common.data_model import BaseModel as PydanticBaseModel
from exceptions import ValidationError


def _parse_iso(value: str) -> datetime:
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


class IntegrationCapability:
    LLM = "llm"
    CALENDAR = "calendar"
    COMMUNICATION = "communication"
    STORAGE = "storage"
    PUSH_NOTIFICATION = "push_notification"


class IntegrationAuthType:
    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    BASIC_AUTH = "basic_auth"
    ACCESS_KEY_SECRET = "access_key_secret"
    CUSTOM = "custom"


class IntegrationStatus:
    CONFIGURED = "configured"
    CONNECTED = "connected"
    ERROR = "error"


class ProviderFieldType:
    TEXT = "text"
    PASSWORD = "password"
    URL = "url"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    EMAIL = "email"


class IntegrationFieldDefinitionContract(PydanticBaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    label: str
    field_type: str = ProviderFieldType.TEXT
    required: bool = False
    secret: bool = False
    help_text: str | None = None
    placeholder: str | None = None


class IntegrationDefinitionContract(PydanticBaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str
    label: str
    description: str
    auth_type: str
    capabilities: tuple[str, ...]
    config_fields: tuple[IntegrationFieldDefinitionContract, ...] = ()
    secret_fields: tuple[IntegrationFieldDefinitionContract, ...] = ()
    supports_validate: bool = True
    supports_authorize: bool = False
    supports_callback: bool = False


class IntegrationAccountContract(PydanticBaseModel):
    model_config = ConfigDict(frozen=True)

    organization_id: str
    user_id: str
    provider: str
    provider_account_id: str
    scopes: tuple[str, ...] = ()
    connected: bool = True


class CalendarEventContract(PydanticBaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    organization_id: str
    user_id: str
    provider: str
    title: str
    starts_at: str
    ends_at: str
    attendees: tuple[str, ...] = ()
    entity_id: str | None = None


class OrganizationIntegrationContract(PydanticBaseModel):
    model_config = ConfigDict(frozen=True)

    organization_id: str
    provider: str
    auth_type: str
    capabilities: tuple[str, ...]
    display_name: str | None = None
    status: str = IntegrationStatus.CONFIGURED
    config: dict[str, Any] = Field(default_factory=dict)
    secret_hints: dict[str, str] = Field(default_factory=dict)
    validation_status: str | None = None
    last_validated_at: str | None = None
    last_error: str | None = None


class CalendarProviderPort(Protocol):
    """Contract for external provider adapters."""

    def has_integration(self, organization_id: str, user_id: str, provider: str) -> bool:
        """Return whether provider account is connected."""
        ...


class ScheduleValidator(Protocol):
    """Contract to validate calendar event times."""

    def validate_window(self, starts_at: str, ends_at: str) -> None:
        """Validate time window semantics."""
        ...


PROVIDER_DEFINITIONS: dict[str, IntegrationDefinitionContract] = {
    "openai": IntegrationDefinitionContract(
        provider="openai",
        label="OpenAI",
        description="API key configuration for GPT and embedding models.",
        auth_type=IntegrationAuthType.API_KEY,
        capabilities=(IntegrationCapability.LLM,),
        secret_fields=(
            IntegrationFieldDefinitionContract(
                name="api_key",
                label="API Key",
                field_type=ProviderFieldType.PASSWORD,
                required=True,
                secret=True,
                placeholder="sk-...",
            ),
        ),
    ),
    "azure_openai": IntegrationDefinitionContract(
        provider="azure_openai",
        label="Azure OpenAI",
        description="Azure OpenAI endpoint, deployment, and API key configuration.",
        auth_type=IntegrationAuthType.API_KEY,
        capabilities=(IntegrationCapability.LLM,),
        config_fields=(
            IntegrationFieldDefinitionContract(
                name="endpoint",
                label="Endpoint",
                field_type=ProviderFieldType.URL,
                required=True,
            ),
            IntegrationFieldDefinitionContract(
                name="api_version",
                label="API Version",
                required=True,
                placeholder="2024-10-21",
            ),
            IntegrationFieldDefinitionContract(
                name="deployment_name",
                label="Deployment Name",
                required=True,
            ),
        ),
        secret_fields=(
            IntegrationFieldDefinitionContract(
                name="api_key",
                label="API Key",
                field_type=ProviderFieldType.PASSWORD,
                required=True,
                secret=True,
            ),
        ),
    ),
    "azure_foundry": IntegrationDefinitionContract(
        provider="azure_foundry",
        label="Microsoft Foundry",
        description="Microsoft Foundry project endpoint and API key configuration.",
        auth_type=IntegrationAuthType.API_KEY,
        capabilities=(IntegrationCapability.LLM,),
        config_fields=(
            IntegrationFieldDefinitionContract(
                name="endpoint",
                label="Foundry Project Endpoint",
                field_type=ProviderFieldType.URL,
                required=True,
                help_text=(
                    "Copy the project endpoint ending in /api/projects/<project-name> "
                    "from the Foundry project overview."
                ),
                placeholder=(
                    "https://resource.services.ai.azure.com/api/projects/project-name"
                ),
            ),
        ),
        secret_fields=(
            IntegrationFieldDefinitionContract(
                name="api_key",
                label="API Key",
                field_type=ProviderFieldType.PASSWORD,
                required=True,
                secret=True,
            ),
        ),
    ),
    "anthropic": IntegrationDefinitionContract(
        provider="anthropic",
        label="Anthropic",
        description="API key configuration for Claude models.",
        auth_type=IntegrationAuthType.API_KEY,
        capabilities=(IntegrationCapability.LLM,),
        secret_fields=(
            IntegrationFieldDefinitionContract(
                name="api_key",
                label="API Key",
                field_type=ProviderFieldType.PASSWORD,
                required=True,
                secret=True,
                placeholder="sk-ant-...",
            ),
        ),
    ),
    "google_gemini": IntegrationDefinitionContract(
        provider="google_gemini",
        label="Google Gemini",
        description="API key configuration for Gemini models.",
        auth_type=IntegrationAuthType.API_KEY,
        capabilities=(IntegrationCapability.LLM,),
        secret_fields=(
            IntegrationFieldDefinitionContract(
                name="api_key",
                label="API Key",
                field_type=ProviderFieldType.PASSWORD,
                required=True,
                secret=True,
            ),
        ),
    ),
    "aws_bedrock": IntegrationDefinitionContract(
        provider="aws_bedrock",
        label="AWS Bedrock",
        description="Amazon Bedrock API key or AWS IAM credentials and region.",
        auth_type=IntegrationAuthType.CUSTOM,
        capabilities=(IntegrationCapability.LLM,),
        config_fields=(
            IntegrationFieldDefinitionContract(
                name="region",
                label="Region",
                required=True,
                placeholder="us-east-1",
            ),
            IntegrationFieldDefinitionContract(
                name="project",
                label="Mantle Project ID",
                required=False,
                help_text="Optional project for Bedrock Mantle usage attribution.",
                placeholder="proj_...",
            ),
            IntegrationFieldDefinitionContract(
                name="api_mode",
                label="Mantle API Mode",
                required=False,
                help_text=(
                    "Optional: auto (recommended), responses, or chat_completions. "
                    "Auto uses AWS model compatibility defaults."
                ),
                placeholder="auto",
            ),
        ),
        secret_fields=(
            IntegrationFieldDefinitionContract(
                name="api_key",
                label="Bedrock API Key",
                field_type=ProviderFieldType.PASSWORD,
                required=False,
                secret=True,
                help_text=(
                    "Recommended for the OpenAI-compatible Bedrock Mantle endpoint. "
                    "Use either this field or AWS credentials below."
                ),
            ),
            IntegrationFieldDefinitionContract(
                name="aws_access_key_id",
                label="AWS Access Key ID",
                required=False,
                secret=True,
                help_text="Optional when the application uses an IAM role credential chain.",
            ),
            IntegrationFieldDefinitionContract(
                name="aws_secret_access_key",
                label="AWS Secret Access Key",
                field_type=ProviderFieldType.PASSWORD,
                required=False,
                secret=True,
            ),
            IntegrationFieldDefinitionContract(
                name="aws_session_token",
                label="AWS Session Token",
                field_type=ProviderFieldType.PASSWORD,
                required=False,
                secret=True,
            ),
        ),
    ),
    "smtp": IntegrationDefinitionContract(
        provider="smtp",
        label="SMTP",
        description="SMTP server credentials for outbound communication.",
        auth_type=IntegrationAuthType.BASIC_AUTH,
        capabilities=(IntegrationCapability.COMMUNICATION,),
        config_fields=(
            IntegrationFieldDefinitionContract(
                name="smtp_host",
                label="SMTP Host",
                required=True,
                placeholder="smtp.example.com",
            ),
            IntegrationFieldDefinitionContract(
                name="smtp_port",
                label="SMTP Port",
                field_type=ProviderFieldType.INTEGER,
                required=True,
                placeholder="587",
            ),
            IntegrationFieldDefinitionContract(
                name="smtp_use_tls",
                label="Use TLS",
                field_type=ProviderFieldType.BOOLEAN,
                required=False,
            ),
            IntegrationFieldDefinitionContract(
                name="from_email",
                label="From Email",
                field_type=ProviderFieldType.EMAIL,
                required=True,
            ),
            IntegrationFieldDefinitionContract(
                name="from_name",
                label="From Name",
                required=False,
            ),
            IntegrationFieldDefinitionContract(
                name="reply_to_email",
                label="Reply To",
                field_type=ProviderFieldType.EMAIL,
                required=False,
            ),
        ),
        secret_fields=(
            IntegrationFieldDefinitionContract(
                name="username",
                label="Username",
                required=True,
                secret=True,
            ),
            IntegrationFieldDefinitionContract(
                name="password",
                label="Password",
                field_type=ProviderFieldType.PASSWORD,
                required=True,
                secret=True,
            ),
        ),
    ),
    "ses": IntegrationDefinitionContract(
        provider="ses",
        label="Amazon SES",
        description="AWS SES API credentials for outbound email.",
        auth_type=IntegrationAuthType.ACCESS_KEY_SECRET,
        capabilities=(IntegrationCapability.COMMUNICATION,),
        config_fields=(
            IntegrationFieldDefinitionContract(
                name="region",
                label="Region",
                required=True,
                placeholder="us-east-1",
            ),
            IntegrationFieldDefinitionContract(
                name="from_email",
                label="From Email",
                field_type=ProviderFieldType.EMAIL,
                required=True,
            ),
            IntegrationFieldDefinitionContract(
                name="from_name",
                label="From Name",
                required=False,
            ),
            IntegrationFieldDefinitionContract(
                name="reply_to_email",
                label="Reply To",
                field_type=ProviderFieldType.EMAIL,
                required=False,
            ),
        ),
        secret_fields=(
            IntegrationFieldDefinitionContract(
                name="aws_access_key_id",
                label="AWS Access Key ID",
                required=True,
                secret=True,
            ),
            IntegrationFieldDefinitionContract(
                name="aws_secret_access_key",
                label="AWS Secret Access Key",
                field_type=ProviderFieldType.PASSWORD,
                required=True,
                secret=True,
            ),
        ),
    ),
    "azure_communication": IntegrationDefinitionContract(
        provider="azure_communication",
        label="Azure Communication Email",
        description="Azure Communication Services Email API configuration.",
        auth_type=IntegrationAuthType.CUSTOM,
        capabilities=(IntegrationCapability.COMMUNICATION,),
        config_fields=(
            IntegrationFieldDefinitionContract(
                name="endpoint", label="Endpoint", field_type=ProviderFieldType.URL, required=True
            ),
            IntegrationFieldDefinitionContract(
                name="from_email",
                label="From Email",
                field_type=ProviderFieldType.EMAIL,
                required=True,
            ),
            IntegrationFieldDefinitionContract(name="from_name", label="From Name", required=False),
            IntegrationFieldDefinitionContract(
                name="reply_to_email",
                label="Reply To",
                field_type=ProviderFieldType.EMAIL,
                required=False,
            ),
        ),
        secret_fields=(
            IntegrationFieldDefinitionContract(
                name="connection_string",
                label="Connection String",
                field_type=ProviderFieldType.PASSWORD,
                required=True,
                secret=True,
            ),
        ),
    ),
    "s3": IntegrationDefinitionContract(
        provider="s3",
        label="Amazon S3",
        description="S3 or S3-compatible object storage configuration.",
        auth_type=IntegrationAuthType.ACCESS_KEY_SECRET,
        capabilities=(IntegrationCapability.STORAGE,),
        config_fields=(
            IntegrationFieldDefinitionContract(name="bucket", label="Bucket", required=True),
            IntegrationFieldDefinitionContract(name="region", label="Region", required=True),
            IntegrationFieldDefinitionContract(
                name="endpoint_url",
                label="Endpoint URL",
                field_type=ProviderFieldType.URL,
                required=False,
            ),
        ),
        secret_fields=(
            IntegrationFieldDefinitionContract(
                name="access_key_id",
                label="Access Key ID",
                required=True,
                secret=True,
            ),
            IntegrationFieldDefinitionContract(
                name="secret_access_key",
                label="Secret Access Key",
                field_type=ProviderFieldType.PASSWORD,
                required=True,
                secret=True,
            ),
        ),
    ),
    "azure_blob": IntegrationDefinitionContract(
        provider="azure_blob",
        label="Azure Blob Storage",
        description="Azure Blob Storage container and account credentials.",
        auth_type=IntegrationAuthType.CUSTOM,
        capabilities=(IntegrationCapability.STORAGE,),
        config_fields=(
            IntegrationFieldDefinitionContract(
                name="account_url",
                label="Account URL",
                field_type=ProviderFieldType.URL,
                required=True,
            ),
            IntegrationFieldDefinitionContract(
                name="container",
                label="Container",
                required=True,
            ),
        ),
        secret_fields=(
            IntegrationFieldDefinitionContract(
                name="connection_string",
                label="Connection String",
                field_type=ProviderFieldType.PASSWORD,
                required=False,
                secret=True,
            ),
            IntegrationFieldDefinitionContract(
                name="account_key",
                label="Account Key",
                field_type=ProviderFieldType.PASSWORD,
                required=False,
                secret=True,
            ),
        ),
    ),
    "google_calendar": IntegrationDefinitionContract(
        provider="google_calendar",
        label="Google Calendar",
        description="OAuth calendar integration for scheduling.",
        auth_type=IntegrationAuthType.OAUTH2,
        capabilities=(IntegrationCapability.CALENDAR,),
        config_fields=(
            IntegrationFieldDefinitionContract(
                name="redirect_uri",
                label="Redirect URI",
                field_type=ProviderFieldType.URL,
                required=False,
            ),
        ),
        supports_validate=False,
        supports_authorize=True,
        supports_callback=True,
    ),
    "google": IntegrationDefinitionContract(
        provider="google",
        label="Google Calendar (Legacy)",
        description="Legacy calendar provider alias retained for modular compatibility.",
        auth_type=IntegrationAuthType.OAUTH2,
        capabilities=(IntegrationCapability.CALENDAR,),
        supports_validate=False,
        supports_authorize=True,
        supports_callback=True,
    ),
    "outlook": IntegrationDefinitionContract(
        provider="outlook",
        label="Outlook Calendar",
        description="Legacy Outlook calendar provider alias.",
        auth_type=IntegrationAuthType.OAUTH2,
        capabilities=(IntegrationCapability.CALENDAR,),
        supports_validate=False,
        supports_authorize=True,
        supports_callback=True,
    ),
    "ics": IntegrationDefinitionContract(
        provider="ics",
        label="ICS Feed",
        description="Legacy ICS calendar provider alias.",
        auth_type=IntegrationAuthType.CUSTOM,
        capabilities=(IntegrationCapability.CALENDAR,),
        supports_validate=False,
    ),
    "azure_notification_hub": IntegrationDefinitionContract(
        provider="azure_notification_hub",
        label="Azure Notification Hub",
        description="Azure Notification Hubs configuration for Android (FCM) push notifications.",
        auth_type=IntegrationAuthType.CUSTOM,
        capabilities=(IntegrationCapability.PUSH_NOTIFICATION,),
        config_fields=(
            IntegrationFieldDefinitionContract(
                name="namespace_name",
                label="Namespace Name",
                required=True,
                placeholder="flowtuple-push-ns",
                help_text="The Azure Notification Hubs namespace name.",
            ),
            IntegrationFieldDefinitionContract(
                name="hub_name",
                label="Hub Name",
                required=True,
                placeholder="flowtuple-push-hub",
                help_text="The notification hub name within the namespace.",
            ),
        ),
        secret_fields=(
            IntegrationFieldDefinitionContract(
                name="connection_string",
                label="Connection String",
                field_type=ProviderFieldType.PASSWORD,
                required=True,
                secret=True,
                help_text="Full SAS connection string from Azure portal (DefaultFullSharedAccessSignature).",
            ),
        ),
        supports_validate=False,
    ),
    "microsoft_graph_email": IntegrationDefinitionContract(
        provider="microsoft_graph_email",
        label="Microsoft Graph Email",
        description="Send emails via Microsoft Graph API using Azure AD app credentials.",
        auth_type=IntegrationAuthType.CUSTOM,
        capabilities=(IntegrationCapability.COMMUNICATION,),
        config_fields=(
            IntegrationFieldDefinitionContract(
                name="tenant_id",
                label="Tenant ID",
                required=True,
            ),
            IntegrationFieldDefinitionContract(
                name="client_id",
                label="Client ID",
                required=True,
            ),
            IntegrationFieldDefinitionContract(
                name="from_email",
                label="From Email",
                field_type=ProviderFieldType.EMAIL,
                required=True,
            ),
            IntegrationFieldDefinitionContract(
                name="from_name",
                label="From Name",
                required=False,
            ),
            IntegrationFieldDefinitionContract(
                name="reply_to_email",
                label="Reply To",
                field_type=ProviderFieldType.EMAIL,
                required=False,
            ),
        ),
        secret_fields=(
            IntegrationFieldDefinitionContract(
                name="client_secret",
                label="Client Secret",
                field_type=ProviderFieldType.PASSWORD,
                required=True,
                secret=True,
            ),
        ),
    ),
}

PROVIDER_ALIASES = {
    "foundry": "azure_foundry",
    "microsoft_foundry": "azure_foundry",
    "azure_foundry": "azure_foundry",
    "google_gemini": "google_gemini",
    "gemini": "google_gemini",
    "bedrock": "aws_bedrock",
    "aws_bedrock": "aws_bedrock",
    "google_calendar": "google_calendar",
}


def list_provider_definitions() -> list[IntegrationDefinitionContract]:
    return sorted(
        PROVIDER_DEFINITIONS.values(),
        key=lambda definition: (definition.capabilities, definition.provider),
    )


def get_provider_definition(provider: str) -> IntegrationDefinitionContract:
    normalized = normalize_provider(provider)
    definition = PROVIDER_DEFINITIONS.get(normalized)
    if definition is None:
        raise ValidationError(f"provider must be one of {sorted(PROVIDER_DEFINITIONS)}")
    return definition


def normalize_provider(provider: str) -> str:
    normalized = str(provider or "").strip().lower()
    normalized = PROVIDER_ALIASES.get(normalized, normalized)
    if normalized not in PROVIDER_DEFINITIONS:
        raise ValidationError(f"provider must be one of {sorted(PROVIDER_DEFINITIONS)}")
    return normalized


def normalize_capability(capability: str) -> str:
    normalized = str(capability or "").strip().lower()
    valid = {
        IntegrationCapability.LLM,
        IntegrationCapability.CALENDAR,
        IntegrationCapability.COMMUNICATION,
        IntegrationCapability.STORAGE,
        IntegrationCapability.PUSH_NOTIFICATION,
    }
    if normalized not in valid:
        raise ValidationError(f"capability must be one of {sorted(valid)}")
    return normalized


def validate_window(starts_at: str, ends_at: str) -> None:
    start = _parse_iso(starts_at)
    end = _parse_iso(ends_at)
    if end <= start:
        raise ValidationError("ends_at must be greater than starts_at")
