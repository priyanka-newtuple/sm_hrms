"""Response models for tools."""

from __future__ import annotations

from pydantic import Field

from common.data_model import BaseModel as PydanticBaseModel

from .interface import (
    ToolDescriptorContract,
    ToolExecutionLogContract,
    ToolExecutionResult,
    ToolPresetContract,
)


class ToolCatalogResponse(PydanticBaseModel):
    """Response contract for the shared tool catalog."""

    tools: list[ToolDescriptorContract] = Field(default_factory=list)
    default_tools: list[str] = Field(default_factory=list)


class ToolPresetListResponse(PydanticBaseModel):
    """Response contract for named tool presets."""

    presets: dict[str, ToolPresetContract] = Field(default_factory=dict)


class ToolExecutionResponse(PydanticBaseModel):
    """Response wrapper for a direct tool execution result."""

    result: ToolExecutionResult


class ToolExecutionLogListResponse(PydanticBaseModel):
    """Response wrapper for paginated tool execution history."""

    items: list[ToolExecutionLogContract] = Field(default_factory=list)
    total: int = 0
