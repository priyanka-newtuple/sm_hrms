from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hrms.models.enums import ApprovalAction, TimesheetStatus


class TimesheetCreate(BaseModel):
    project_id: uuid.UUID
    week_start_date: date
    hours: float
    notes: str | None = None
    work_date: date | None = None
    task_details: str | None = Field(default=None, max_length=2000)


class TimesheetUpdate(BaseModel):
    hours: float | None = None
    notes: str | None = None
    task_details: str | None = Field(default=None, max_length=2000)


class TimesheetApprovalIn(BaseModel):
    action: ApprovalAction
    comment: str | None = None


class TimesheetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    employee_id: uuid.UUID
    project_id: uuid.UUID
    week_start_date: date
    work_date: date | None = None
    hours: float
    status: TimesheetStatus
    notes: str | None
    task_details: str | None = None
    submitted_at: datetime | None


class WeekEntryIn(BaseModel):
    project_id: uuid.UUID
    work_date: date
    hours: float = Field(ge=0, le=24)
    task_details: str | None = Field(default=None, max_length=2000)


class WeekSaveIn(BaseModel):
    week_start_date: date
    entries: list[WeekEntryIn] = Field(max_length=100)


class HolidayIn(BaseModel):
    holiday_date: date
    name: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    is_optional: bool = False


class HolidayOut(HolidayIn):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class LeaveCreate(BaseModel):
    start_date: date
    end_date: date
    leave_type: str = Field(pattern="^(annual|sick|casual|unpaid|other)$")
    reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def valid_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        return self


class LeaveDecisionIn(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    comment: str | None = Field(default=None, max_length=2000)


class LeaveOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str | None = None
    manager_id: uuid.UUID | None
    start_date: date
    end_date: date
    leave_type: str
    reason: str | None
    status: str
    decision_comment: str | None
    decided_at: datetime | None
