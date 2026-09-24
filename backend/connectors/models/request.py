"""API request contracts for connectors."""

from __future__ import annotations

from typing import Any, Self

from pydantic import Field, model_validator

from common.data_model import BaseModel as PydanticBaseModel
from exceptions import ValidationError

from connectors.models.interface import (
    ConnectorAuthType,
    ContentType,
    HttpMethod,
    normalize_auth_type,
    normalize_content_type,
    normalize_method,
)


class ConnectorCreateRequest(PydanticBaseModel):
    """Payload to create a connector. `secrets` is write-only and never returned."""

    name: str = Field(..., min_length=1, max_length=128)
    entity_types: list[str] = Field(default_factory=list)
    base_url: str = Field(..., min_length=1, max_length=512)
    method: str = HttpMethod.POST
    path: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    query_params: dict[str, str] = Field(default_factory=dict)
    content_type: str = ContentType.JSON
    body_template: dict[str, Any] | list[Any] | str | None = None
    auth_type: str = ConnectorAuthType.NONE
    auth_config: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, str] = Field(default_factory=dict)
    response_mapping: dict[str, str] = Field(default_factory=dict)
    success_when: dict[str, Any] = Field(default_factory=dict)
    expose_as_tool: bool = False

    @model_validator(mode="after")
    def normalize(self) -> Self:
        """Strip and normalize the enum-like fields so persistence stores canonical values."""
        self.name = self.name.strip()
        cleaned = [t.strip() for t in self.entity_types if t and t.strip()]
        self.entity_types = list(dict.fromkeys(cleaned))
        self.base_url = self.base_url.strip()
        self.path = (self.path or "").strip()
        self.method = normalize_method(self.method)
        self.auth_type = normalize_auth_type(self.auth_type)
        self.content_type = normalize_content_type(self.content_type)
        return self

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Self:
        """Validate a raw dict into a request, raising ValidationError on bad input."""
        try:
            return cls.model_validate(payload)
        except Exception as exc:
            raise ValidationError(f"Invalid connector create payload: {exc}") from exc


class ConnectorUpdateRequest(PydanticBaseModel):
    """Payload to update a connector. Every field is optional; omitted fields are unchanged."""

    name: str | None = Field(default=None, max_length=128)
    entity_types: list[str] | None = None
    base_url: str | None = Field(default=None, max_length=512)
    method: str | None = None
    path: str | None = None
    headers: dict[str, str] | None = None
    query_params: dict[str, str] | None = None
    content_type: str | None = None
    body_template: dict[str, Any] | list[Any] | str | None = None
    auth_type: str | None = None
    auth_config: dict[str, Any] | None = None
    secrets: dict[str, str] | None = None
    response_mapping: dict[str, str] | None = None
    success_when: dict[str, Any] | None = None
    expose_as_tool: bool | None = None
    status: str | None = None

    @model_validator(mode="after")
    def normalize(self) -> Self:
        """Normalize only the fields that were provided."""
        if self.method is not None:
            self.method = normalize_method(self.method)
        if self.auth_type is not None:
            self.auth_type = normalize_auth_type(self.auth_type)
        if self.content_type is not None:
            self.content_type = normalize_content_type(self.content_type)
        if self.name is not None:
            self.name = self.name.strip()
        if self.entity_types is not None:
            cleaned = [t.strip() for t in self.entity_types if t and t.strip()]
            self.entity_types = list(dict.fromkeys(cleaned))
        return self

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Self:
        """Validate a raw dict into a request, raising ValidationError on bad input."""
        try:
            return cls.model_validate(payload)
        except Exception as exc:
            raise ValidationError(f"Invalid connector update payload: {exc}") from exc


class ConnectorTestRequest(PydanticBaseModel):
    """Payload to test a connector against sample entity field values."""

    sample_fields: dict[str, Any] = Field(default_factory=dict)


class ConnectorInlineTestRequest(PydanticBaseModel):
    """Test a connector definition inline without saving it first."""

    connector: ConnectorCreateRequest
    sample_fields: dict[str, Any] = Field(default_factory=dict)
    # When testing an already-saved connector, this lets the call reuse its stored
    # secrets for any credential the user left blank in the form.
    connector_id: str | None = None
