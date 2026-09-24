"""Request models for recurring entity schedules."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import Field, model_validator

from common.data_model import BaseModel
from schedules.models.interface import (
    RecurrenceRule,
    ScheduleCondition,
    ScheduleFrequency,
    ScheduleTargetScope,
)


class ScheduleCreateRequest(BaseModel):
    machine_name: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    anchor_entity_type_id: str = Field(..., min_length=1, max_length=36)
    relation_def_id: str = Field(..., min_length=1, max_length=36)
    target_scope: ScheduleTargetScope = ScheduleTargetScope.ALL
    recurrence: RecurrenceRule
    occurrences_per_batch: int = Field(default=1, ge=1, le=24)
    lead_days: int = Field(default=30, ge=0, le=366)
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    entity_data: dict[str, Any] = Field(default_factory=dict)
    identifier_template: str = Field(
        default="{schedule_name} - {anchor_identifier} - {due_date}",
        min_length=1,
        max_length=512,
    )
    owner_id: str | None = None
    assignee_id: str | None = None
    conditions: list[ScheduleCondition] = Field(default_factory=list)
    condition_mode: str = "all"
    is_enabled: bool = True
    starts_on: date | None = None
    ends_on: date | None = None
    anchor_entity_ids: list[str] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def normalize(self) -> "ScheduleCreateRequest":
        self.machine_name = self.machine_name.strip()
        self.name = self.name.strip()
        self.description = self.description.strip() if self.description else None
        self.timezone = self.timezone.strip()
        self.condition_mode = self.condition_mode.strip().lower()
        if self.condition_mode not in {"all", "any"}:
            raise ValueError("condition_mode must be 'all' or 'any'")
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValueError("ends_on must be on or after starts_on")
        if self.recurrence.frequency == ScheduleFrequency.ONCE:
            if self.occurrences_per_batch != 1:
                raise ValueError("one-time schedules create exactly one occurrence")
            if self.starts_on is not None or self.ends_on is not None:
                raise ValueError("one-time schedules use occurs_on instead of start or end dates")
        self.anchor_entity_ids = list(
            dict.fromkeys(
                _non_empty_id(entity_id, "anchor_entity_ids")
                for entity_id in self.anchor_entity_ids
            )
        )
        # Preserve the pre-scope API contract: supplying entity IDs meant the
        # caller intentionally selected those records.
        if self.anchor_entity_ids and "target_scope" not in self.model_fields_set:
            self.target_scope = ScheduleTargetScope.SELECTED
        if self.target_scope == ScheduleTargetScope.ALL and self.anchor_entity_ids:
            raise ValueError("all target scope cannot include anchor_entity_ids")
        if self.target_scope == ScheduleTargetScope.SELECTED and not self.anchor_entity_ids:
            raise ValueError("selected target scope requires at least one anchor_entity_id")
        return self


class ScheduleUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    recurrence: RecurrenceRule | None = None
    occurrences_per_batch: int | None = Field(default=None, ge=1, le=24)
    lead_days: int | None = Field(default=None, ge=0, le=366)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    entity_data: dict[str, Any] | None = None
    identifier_template: str | None = Field(default=None, min_length=1, max_length=512)
    owner_id: str | None = None
    assignee_id: str | None = None
    conditions: list[ScheduleCondition] | None = None
    condition_mode: str | None = None
    is_enabled: bool | None = None
    starts_on: date | None = None
    ends_on: date | None = None

    @model_validator(mode="after")
    def normalize(self) -> "ScheduleUpdateRequest":
        if self.name is not None:
            self.name = self.name.strip()
        if self.description is not None:
            self.description = self.description.strip() or None
        if self.timezone is not None:
            self.timezone = self.timezone.strip()
        if self.condition_mode is not None:
            self.condition_mode = self.condition_mode.strip().lower()
            if self.condition_mode not in {"all", "any"}:
                raise ValueError("condition_mode must be 'all' or 'any'")
        return self


class ScheduleTargetCreateRequest(BaseModel):
    anchor_entity_id: str = Field(..., min_length=1, max_length=36)
    assignee_id: str | None = None
    is_enabled: bool = True

    @model_validator(mode="after")
    def normalize(self) -> "ScheduleTargetCreateRequest":
        self.anchor_entity_id = self.anchor_entity_id.strip()
        self.assignee_id = self.assignee_id.strip() if self.assignee_id else None
        return self


class ScheduleRunNowRequest(BaseModel):
    invocation_id: str = Field(..., min_length=1, max_length=128)

    @model_validator(mode="after")
    def normalize(self) -> "ScheduleRunNowRequest":
        self.invocation_id = _non_empty_id(self.invocation_id, "invocation_id")
        return self


def _non_empty_id(value: str, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot contain empty values")
    return normalized
