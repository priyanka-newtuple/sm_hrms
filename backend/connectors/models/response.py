"""API response contracts for connectors."""

from __future__ import annotations

from typing import Any

from pydantic import ConfigDict, Field

from common.data_model import BaseModel as PydanticBaseModel

from connectors.models.interface import ConnectorAuthType, ConnectorStatus, ContentType, HttpMethod


class ConnectorReadResponse(PydanticBaseModel):
    """Public view of a connector. Carries masked secret hints, never the raw secret."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    name: str
    entity_types: list[str] = Field(default_factory=list)
    base_url: str
    method: str = HttpMethod.POST
    path: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    query_params: dict[str, str] = Field(default_factory=dict)
    content_type: str = ContentType.JSON
    body_template: dict[str, Any] | list[Any] | str | None = None
    auth_type: str = ConnectorAuthType.NONE
    auth_config: dict[str, Any] = Field(default_factory=dict)
    secret_hints: dict[str, str] = Field(default_factory=dict)
    response_mapping: dict[str, str] = Field(default_factory=dict)
    success_when: dict[str, Any] = Field(default_factory=dict)
    expose_as_tool: bool = False
    status: str = ConnectorStatus.CONFIGURED
    validation_status: str | None = None
    last_validated_at: str | None = None
    last_error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ConnectorListResponse(PydanticBaseModel):
    """List of connectors for an organization."""

    model_config = ConfigDict(from_attributes=True)

    items: list[ConnectorReadResponse] = Field(default_factory=list)
    total: int = 0


class ConnectorsStatusResponse(PydanticBaseModel):
    """Module health/status response."""

    module: str
    status: str
    started: bool


class ConnectorTestResponse(PydanticBaseModel):
    """Result of a connector test call."""

    success: bool
    status_code: int | None = None
    message: str = ""
    response_json: Any | None = None
