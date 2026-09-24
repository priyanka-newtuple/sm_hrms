"""Response models for integrations."""

from __future__ import annotations

from typing import Any

from pydantic import ConfigDict, Field

from common.data_model import BaseModel as PydanticBaseModel


class IntegrationsCalendarStatusResponse(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    module: str
    status: str
    started: bool


class IntegrationFieldDefinitionResponse(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    label: str
    field_type: str
    required: bool
    secret: bool
    help_text: str | None = None
    placeholder: str | None = None


class IntegrationDefinitionResponse(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider: str
    label: str
    description: str
    auth_type: str
    capabilities: list[str] = Field(default_factory=list)
    config_fields: list[IntegrationFieldDefinitionResponse] = Field(default_factory=list)
    secret_fields: list[IntegrationFieldDefinitionResponse] = Field(default_factory=list)
    supports_validate: bool = True
    supports_authorize: bool = False
    supports_callback: bool = False


class IntegrationDefinitionsListResponse(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[IntegrationDefinitionResponse] = Field(default_factory=list)


class IntegrationValidationResponse(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider: str
    valid: bool
    message: str


class TestEmailResponse(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    success: bool
    message: str
    message_id: str | None = None


class CapabilityDefaultResponse(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    capability: str
    provider: str | None = None


class CapabilityDefaultsListResponse(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    organization_id: str
    items: list[CapabilityDefaultResponse] = Field(default_factory=list)


class OrganizationIntegrationResponse(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    organization_id: str
    provider: str
    label: str
    auth_type: str
    capabilities: list[str] = Field(default_factory=list)
    configured: bool = True
    status: str = "configured"
    display_name: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    secret_hints: dict[str, str] = Field(default_factory=dict)
    validation_status: str | None = None
    last_validated_at: str | None = None
    last_error: str | None = None
    is_default_for: list[str] = Field(default_factory=list)


class OrganizationIntegrationsListResponse(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    organization_id: str
    items: list[OrganizationIntegrationResponse] = Field(default_factory=list)


class IntegrationConnectionResponse(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    organization_id: str
    user_id: str
    provider: str
    provider_account_id: str
    connected: bool
    scopes: list[str] = Field(default_factory=list)


class CalendarEventResponse(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: str
    organization_id: str
    user_id: str
    provider: str
    title: str
    starts_at: str
    ends_at: str
    attendees: list[str] = Field(default_factory=list)
    entity_id: str | None = None


class CalendarEventsListResponse(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[CalendarEventResponse] = Field(default_factory=list)


class IntegrationConnectionsListResponse(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    organization_id: str
    items: list[IntegrationConnectionResponse] = Field(default_factory=list)
