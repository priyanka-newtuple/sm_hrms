"""Request models for integrations."""

from __future__ import annotations

from typing import Any, Self

from pydantic import ConfigDict, EmailStr, Field, ValidationInfo, field_validator, model_validator

from common.data_model import BaseModel as PydanticBaseModel
from integrations.models.interface import normalize_capability, normalize_provider, validate_window


class SendTestEmailRequest(PydanticBaseModel):
    """Recipient for a test email sent via a communication provider.

    When `config`/`secrets` are supplied, the test is sent ad-hoc using those
    values (so a provider can be tested before it is saved); secret fields left
    blank fall back to the saved credentials. When omitted, the saved
    configuration is used.
    """

    to_email: EmailStr = Field(..., description="Address to send the test email to")
    config: dict[str, Any] = Field(default_factory=dict, description="Unsaved provider config to test with")
    secrets: dict[str, Any] = Field(default_factory=dict, description="Unsaved provider secrets to test with")


def _non_empty(value: object, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def _optional_text(value: object | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


class ConnectIntegrationRequest(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    organization_id: str
    user_id: str
    provider: str
    provider_account_id: str
    scopes: list[str] = Field(default_factory=list)

    @field_validator("organization_id", "user_id", "provider_account_id", mode="before")
    @classmethod
    def _validate_non_empty(cls, value: object, info: ValidationInfo) -> str:
        return _non_empty(value, info.field_name or "value")

    @field_validator("provider", mode="before")
    @classmethod
    def _normalize_provider(cls, value: object) -> str:
        return normalize_provider(str(value or ""))

    @field_validator("scopes", mode="before")
    @classmethod
    def _normalize_scopes(cls, value: object) -> list[str]:
        if value in (None, ""):
            return []
        if not isinstance(value, list):
            raise ValueError("scopes must be a list")
        return sorted({str(scope).strip() for scope in value if str(scope).strip()})


class UpsertOrganizationIntegrationRequest(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    display_name: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, Any] = Field(default_factory=dict)
    validate_provider: bool = Field(default=True, alias="validate")
    set_default: bool = False

    @field_validator("display_name", mode="before")
    @classmethod
    def _normalize_display_name(cls, value: object) -> str | None:
        return _optional_text(value)

    @field_validator("config", "secrets", mode="before")
    @classmethod
    def _normalize_payload(cls, value: object, info: ValidationInfo) -> dict[str, Any]:
        if value in (None, ""):
            return {}
        if not isinstance(value, dict):
            raise ValueError(f"{info.field_name} must be an object")
        return dict(value)


class ValidateOrganizationIntegrationRequest(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    config: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, Any] = Field(default_factory=dict)

    @field_validator("config", "secrets", mode="before")
    @classmethod
    def _normalize_payload(cls, value: object, info: ValidationInfo) -> dict[str, Any]:
        if value in (None, ""):
            return {}
        if not isinstance(value, dict):
            raise ValueError(f"{info.field_name} must be an object")
        return dict(value)


class SetCapabilityDefaultRequest(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider: str

    @field_validator("provider", mode="before")
    @classmethod
    def _normalize_provider(cls, value: object) -> str:
        return normalize_provider(str(value or ""))


class ScheduleCalendarEventRequest(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    organization_id: str
    user_id: str
    provider: str
    title: str
    starts_at: str
    ends_at: str
    attendees: list[str] = Field(default_factory=list)
    entity_id: str | None = None

    @field_validator("organization_id", "user_id", "title", "starts_at", "ends_at", mode="before")
    @classmethod
    def _validate_non_empty(cls, value: object, info: ValidationInfo) -> str:
        return _non_empty(value, info.field_name or "value")

    @field_validator("provider", mode="before")
    @classmethod
    def _normalize_provider(cls, value: object) -> str:
        return normalize_provider(str(value or ""))

    @field_validator("attendees", mode="before")
    @classmethod
    def _normalize_attendees(cls, value: object) -> list[str]:
        if value in (None, ""):
            return []
        if not isinstance(value, list):
            raise ValueError("attendees must be a list")
        return sorted({str(attendee).strip() for attendee in value if str(attendee).strip()})

    @field_validator("entity_id", mode="before")
    @classmethod
    def _normalize_entity_id(cls, value: object) -> str | None:
        return _optional_text(value)

    @model_validator(mode="after")
    def _validate_window(self) -> Self:
        validate_window(starts_at=self.starts_at, ends_at=self.ends_at)
        return self


class ListCalendarEventsRequest(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    organization_id: str
    provider: str | None = None
    user_id: str | None = None

    @field_validator("organization_id", mode="before")
    @classmethod
    def _validate_organization_id(cls, value: object) -> str:
        return _non_empty(value, "organization_id")

    @field_validator("provider", mode="before")
    @classmethod
    def _normalize_provider(cls, value: object) -> str | None:
        if value in (None, ""):
            return None
        return normalize_provider(str(value))

    @field_validator("user_id", mode="before")
    @classmethod
    def _normalize_user_id(cls, value: object) -> str | None:
        return _optional_text(value)


class CapabilityScopeRequest(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    capability: str

    @field_validator("capability", mode="before")
    @classmethod
    def _normalize_capability(cls, value: object) -> str:
        return normalize_capability(str(value or ""))
