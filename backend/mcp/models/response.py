"""Response models for platform-managed MCP capabilities."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from common.data_model import BaseModel as PydanticBaseModel


class McpServerPackageResponse(PydanticBaseModel):
    id: str
    server_key: str
    name: str
    description: str | None = None
    version: str
    is_platform_managed: bool
    is_active: bool
    is_enabled: bool
    config: dict[str, Any] = Field(default_factory=dict)


class McpCapabilityResponse(PydanticBaseModel):
    id: str
    server_package_id: str
    capability_key: str
    tool_id: str
    display_name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] | None = None
    category: str
    is_mutating: bool
    requires_approval: bool
    package_enabled: bool
    is_enabled: bool
    is_active: bool


class McpToolingOverviewResponse(PydanticBaseModel):
    packages: list[McpServerPackageResponse] = Field(default_factory=list)
    capabilities: list[McpCapabilityResponse] = Field(default_factory=list)

