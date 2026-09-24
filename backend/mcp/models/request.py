"""Request models for MCP package configuration."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from common.data_model import BaseModel as PydanticBaseModel


class McpServerConfigurationUpdate(PydanticBaseModel):
    is_enabled: bool
    config: dict[str, Any] = Field(default_factory=dict)


class McpCapabilityConfigurationUpdate(PydanticBaseModel):
    is_enabled: bool
    requires_approval: bool | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    integration_ref: str | None = None

