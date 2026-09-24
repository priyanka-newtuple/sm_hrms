"""Interface models and contracts for tasks."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Protocol

from pydantic import ConfigDict, Field

try:
    from common.data_model import BaseModel as PydanticBaseModel
except ImportError:  # pragma: no cover - package import fallback
    from backend.modular_backend.common.data_model import BaseModel as PydanticBaseModel


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class TaskPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class TaskSource(str, Enum):
    MANUAL = "manual"
    AUTO = "auto"


class TaskContract(PydanticBaseModel):
    model_config = ConfigDict(frozen=True)

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


class TaskReadPort(Protocol):
    """Read contract consumed by dependent managers."""

    def list_entity_tasks(
        self,
        organization_id: str,
        entity_id: str,
        status: str | None = None,
        stage: str | None = None,
        include_archived: bool = False,
    ) -> list[TaskContract]:
        """Return tasks for an entity."""

    def has_incomplete_tasks_for_stage(
        self,
        organization_id: str,
        entity_id: str,
        stage: str,
        source: str | None = None,
    ) -> bool:
        """Return whether incomplete tasks exist for a stage."""
