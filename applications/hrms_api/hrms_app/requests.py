"""HRMS-specific request validation before using generic platform services."""

from __future__ import annotations

from datetime import date
from typing import Any, Self

from pydantic import BaseModel, EmailStr, Field, model_validator


class LeaveCreateRequest(BaseModel):
    start_date: date
    end_date: date
    leave_type: str
    reason: str | None = Field(default=None, max_length=5000)
    custom: dict[str, Any] = Field(default_factory=dict)  # fields the organization added in Settings
    idempotency_key: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def validate_dates(self) -> Self:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if self.reason is not None:
            self.reason = self.reason.strip() or None
        return self


class EmployeeCreateRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    work_email: EmailStr
    department: str | None = Field(default=None, max_length=100)
    designation: str | None = Field(default=None, max_length=100)
    role: str = Field(default='hrms_employee', min_length=1, max_length=128)
    reports_to_entity_id: str | None = None
    date_joined: date
    employment_type: str = "full_time"
    work_location: str | None = Field(default=None, max_length=100)
    notice_period_days: int | None = Field(default=None, ge=0, le=365)
    phone: str | None = Field(default=None, max_length=30)
    custom: dict[str, Any] = Field(default_factory=dict)  # fields the organization added in Settings
    idempotency_key: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def normalize_text(self) -> Self:
        for field in ("first_name", "last_name", "department", "designation"):
            if getattr(self, field) is None:
                continue
            value = str(getattr(self, field)).strip()
            if not value:
                raise ValueError(f"{field} must not be blank")
            setattr(self, field, value)
        return self


class EmployeeUpdateRequest(BaseModel):
    """Job and personal details HR may correct after hiring. Identity (work email, employee code)
    and access role are changed elsewhere."""
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    department: str | None = Field(default=None, max_length=100)
    designation: str | None = Field(default=None, max_length=100)
    reports_to_entity_id: str | None = None
    date_joined: date
    employment_type: str = "full_time"
    work_location: str | None = Field(default=None, max_length=100)
    notice_period_days: int | None = Field(default=None, ge=0, le=365)
    phone: str | None = Field(default=None, max_length=30)
    custom: dict[str, Any] = Field(default_factory=dict)  # fields the organization added in Settings
    idempotency_key: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def normalize_text(self) -> Self:
        for field in ("first_name", "last_name", "department", "designation"):
            if getattr(self, field) is None:
                continue
            value = str(getattr(self, field)).strip()
            if not value:
                raise ValueError(f"{field} must not be blank")
            setattr(self, field, value)
        return self


class EmployeeExitRequest(BaseModel):
    """An employee leaving: the last working day decides whether they are on notice or offboarded."""
    last_working_day: date
    # did_not_join: a hire who never started (no-show, withdrawn offer); offboarded straight away.
    reason: str
    note: str | None = Field(default=None, max_length=2000)
    idempotency_key: str = Field(min_length=8, max_length=128)


class OnboardingStepUpdateRequest(BaseModel):
    """Hand a step to someone else, move its due date, or both."""
    assigned_to: str | None = Field(default=None, max_length=64)
    due_date: date | None = None

    @model_validator(mode="after")
    def something_changes(self) -> Self:
        if not self.assigned_to and not self.due_date:
            raise ValueError("Choose a new owner or a new due date")
        return self


class OnboardingReasonRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class EmployeeOperationRequest(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=128)
