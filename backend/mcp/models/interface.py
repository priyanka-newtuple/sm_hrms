"""Interface contracts for platform-managed MCP capabilities."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import ConfigDict, Field

from common.data_model import BaseModel as PydanticBaseModel


class McpServerPackageContract(PydanticBaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: str
    server_key: str
    name: str
    description: str | None = None
    version: str
    is_platform_managed: bool = True
    is_active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata_json")
    created_at: datetime
    updated_at: datetime | None = None


class McpServerConfigurationContract(PydanticBaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: str
    organization_id: str
    server_package_id: str
    is_enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict, alias="config_json")
    created_by: str | None = None
    updated_by: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class McpCapabilityContract(PydanticBaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: str
    server_package_id: str
    capability_key: str
    tool_id: str
    display_name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] | None = None
    category: str
    default_requires_approval: bool = False
    default_is_mutating: bool = False
    is_active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata_json")
    created_at: datetime
    updated_at: datetime | None = None


class McpCapabilityConfigurationContract(PydanticBaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: str
    organization_id: str
    capability_id: str
    is_enabled: bool = True
    requires_approval: bool = False
    config: dict[str, Any] = Field(default_factory=dict, alias="config_json")
    integration_ref: str | None = None
    created_by: str | None = None
    updated_by: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class McpCapabilityView(PydanticBaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    server_package_id: str
    capability_key: str
    tool_id: str
    display_name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] | None = None
    category: str
    is_mutating: bool = False
    requires_approval: bool = False
    package_enabled: bool = True
    is_enabled: bool = True
    is_active: bool = True

