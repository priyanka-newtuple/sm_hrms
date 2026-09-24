"""Response models for tasks."""

from __future__ import annotations

from datetime import datetime

from pydantic import ConfigDict, Field

try:
    from common.data_model import BaseModel as PydanticBaseModel
except ImportError:  # pragma: no cover - package import fallback
    from backend.modular_backend.common.data_model import BaseModel as PydanticBaseModel


class TaskReadResponse(PydanticBaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    entity_id: str
    entity_type: str
    title: str
    description: str | None = None
    assigned_to: str | None = None
    created_by: str
    status: str
    priority: str
    due_date: datetime | None = None
    stage: str | None = None
    source: str
    completed_at: datetime | None = None
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None
    assigned_to_name: str | None = None
    created_by_name: str | None = None


class TaskListResponse(PydanticBaseModel):
    tasks: list[TaskReadResponse] = Field(default_factory=list)
    total: int = 0


class TasksStatusResponse(PydanticBaseModel):
    module: str
    status: str
    started: bool
