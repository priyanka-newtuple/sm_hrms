"""Response models for executor runtime operations."""

from __future__ import annotations

from pydantic import Field

from common.data_model import BaseModel as PydanticBaseModel
from executor.models.interface import ExecutorDefinition, ExecutorResponse


class ExecutorExecutionResponse(PydanticBaseModel):
    """Wrap the result of one executor execution."""

    executor: ExecutorDefinition
    result: ExecutorResponse
    resolved_trigger: str | None = None


class ExecutorCatalogResponse(PydanticBaseModel):
    """Return the currently registered executor definitions."""

    executors: list[ExecutorDefinition] = Field(default_factory=list)
