"""Request models for tasks."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

try:
    from common.data_model import BaseModel as PydanticBaseModel
except ImportError:  # pragma: no cover - package import fallback
    from backend.modular_backend.common.data_model import BaseModel as PydanticBaseModel

try:
    from exceptions import ValidationError
except ImportError:  # pragma: no cover - package import fallback
    from backend.modular_backend.exceptions import ValidationError


class TaskCreateRequest(PydanticBaseModel):
    title: str = Field(..., min_length=1, max_length=256)
    description: str | None = None
    assigned_to: str | None = None
    priority: str = Field(default="MEDIUM")
    due_date: datetime | None = None
    entity_type: str | None = None

    @model_validator(mode="after")
    def normalize_fields(self) -> "TaskCreateRequest":
        self.title = str(self.title).strip()
        self.description = self.description.strip() if self.description else None
        self.assigned_to = self.assigned_to.strip() if self.assigned_to else None
        self.priority = str(self.priority).strip().upper()
        self.entity_type = self.entity_type.strip() if self.entity_type else None
        return self

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "TaskCreateRequest":
        try:
            return cls.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            raise ValidationError(str(exc)) from exc


class TaskUpdateRequest(PydanticBaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=256)
    description: str | None = None
    assigned_to: str | None = None
    status: str | None = None
    priority: str | None = None
    due_date: datetime | None = None

    @model_validator(mode="after")
    def normalize_fields(self) -> "TaskUpdateRequest":
        if self.title is not None:
            self.title = str(self.title).strip()
        if self.description is not None:
            self.description = self.description.strip()
        if self.assigned_to is not None:
            self.assigned_to = self.assigned_to.strip()
        if self.status is not None:
            self.status = str(self.status).strip().upper()
        if self.priority is not None:
            self.priority = str(self.priority).strip().upper()
        return self

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "TaskUpdateRequest":
        try:
            return cls.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            raise ValidationError(str(exc)) from exc


class TaskListRequest(PydanticBaseModel):
    organization_id: str
    assigned_to: str | None = None
    status: str | None = None
    entity_type: str | None = None
    priority: str | None = None
    due_before: datetime | None = None
    due_after: datetime | None = None
    skip: int = 0
    limit: int = 50

    @model_validator(mode="after")
    def normalize_fields(self) -> "TaskListRequest":
        self.organization_id = str(self.organization_id).strip()
        self.assigned_to = self.assigned_to.strip() if self.assigned_to else None
        self.status = self.status.strip().upper() if self.status else None
        self.entity_type = self.entity_type.strip() if self.entity_type else None
        self.priority = self.priority.strip().upper() if self.priority else None
        return self


class EntityTaskListRequest(PydanticBaseModel):
    organization_id: str
    entity_id: str
    status: str | None = None

    @model_validator(mode="after")
    def normalize_fields(self) -> "EntityTaskListRequest":
        self.organization_id = str(self.organization_id).strip()
        self.entity_id = str(self.entity_id).strip()
        self.status = self.status.strip().upper() if self.status else None
        return self
