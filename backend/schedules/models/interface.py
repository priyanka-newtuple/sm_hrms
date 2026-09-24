"""Typed contracts for recurring entity schedules."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import Field, model_validator

from common.data_model import BaseModel


class ScheduleFrequency(StrEnum):
    ONCE = "once"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"


class ScheduleActivationPolicy(StrEnum):
    CURRENT_PERIOD = "current_period"
    NEXT_OCCURRENCE = "next_occurrence"


class ScheduleTargetScope(StrEnum):
    ALL = "all"
    SELECTED = "selected"


class ScheduleConditionOperator(StrEnum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    IN = "in"
    NOT_IN = "not_in"
    EXISTS = "exists"
    NOT_EXISTS = "not_exists"


class ScheduleCondition(BaseModel):
    field: str = Field(..., min_length=1, max_length=128)
    operator: ScheduleConditionOperator
    value: Any = None

    @model_validator(mode="after")
    def normalize(self) -> "ScheduleCondition":
        self.field = self.field.strip()
        if self.operator in {ScheduleConditionOperator.IN, ScheduleConditionOperator.NOT_IN}:
            if not isinstance(self.value, list) or not self.value:
                raise ValueError(f"{self.operator.value} conditions require a non-empty list")
        if self.operator not in {
            ScheduleConditionOperator.EXISTS,
            ScheduleConditionOperator.NOT_EXISTS,
        } and self.value is None:
            raise ValueError(f"{self.operator.value} conditions require a value")
        return self


class RecurrenceRule(BaseModel):
    frequency: ScheduleFrequency
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    months: list[int] = Field(default_factory=list)
    occurs_on: date | None = None

    @model_validator(mode="after")
    def validate_months(self) -> "RecurrenceRule":
        self.months = sorted(set(self.months))
        if any(month < 1 or month > 12 for month in self.months):
            raise ValueError("months must contain values between 1 and 12")
        if self.frequency == ScheduleFrequency.ONCE:
            if self.occurs_on is None:
                raise ValueError("one-time schedules require occurs_on")
            self.day_of_month = None
            self.months = []
            return self
        if self.day_of_month is None:
            raise ValueError("recurring schedules require day_of_month")
        self.occurs_on = None
        if self.frequency == ScheduleFrequency.QUARTERLY and len(self.months) != 4:
            raise ValueError("quarterly schedules require exactly four months")
        if self.frequency == ScheduleFrequency.ANNUAL and len(self.months) != 1:
            raise ValueError("annual schedules require exactly one month")
        if self.frequency == ScheduleFrequency.MONTHLY:
            self.months = []
        return self


class ScheduleRecord(BaseModel):
    schedule_id: str
    organization_id: str
    machine_name: str
    name: str
    description: str | None = None
    anchor_entity_type_id: str
    target_entity_type_id: str
    relation_def_id: str
    target_scope: ScheduleTargetScope = ScheduleTargetScope.ALL
    recurrence: RecurrenceRule
    occurrences_per_batch: int = 1
    lead_days: int
    timezone: str
    entity_data: dict[str, Any] = Field(default_factory=dict)
    identifier_template: str
    owner_id: str | None = None
    assignee_id: str | None = None
    conditions: list[ScheduleCondition] = Field(default_factory=list)
    condition_mode: str = "all"
    is_enabled: bool = True
    starts_on: date | None = None
    ends_on: date | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None


class ScheduleTargetRecord(BaseModel):
    target_id: str
    organization_id: str
    schedule_id: str
    anchor_entity_id: str
    next_due_date: date
    next_materialization_date: date
    assignee_id: str | None = None
    is_enabled: bool = True
    last_action_run_id: str | None = None
    last_result: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
