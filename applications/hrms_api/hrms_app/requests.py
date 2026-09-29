"""HRMS-specific request validation before using generic platform services."""

from __future__ import annotations

from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, EmailStr, Field, model_validator


class LeaveCreateRequest(BaseModel):
    start_date: date
    end_date: date
    leave_type: Literal["annual", "sick", "casual", "unpaid", "other"]
    reason: str | None = Field(default=None, max_length=5000)
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
    department: str = Field(min_length=1, max_length=100)
    designation: str = Field(min_length=1, max_length=100)
    role: Literal["hrms_employee", "hrms_manager", "hrms_hr_basic", "hrms_hr_full"] = (
        "hrms_employee"
    )
    reports_to_entity_id: str | None = None
    date_joined: date
    employment_type: Literal["full_time", "contract", "intern"] = "full_time"
    work_location: str | None = Field(default=None, max_length=100)
    notice_period_days: int | None = Field(default=None, ge=0, le=365)
    phone: str | None = Field(default=None, max_length=30)
    idempotency_key: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def normalize_text(self) -> Self:
        for field in ("first_name", "last_name", "department", "designation"):
            value = str(getattr(self, field)).strip()
            if not value:
                raise ValueError(f"{field} must not be blank")
            setattr(self, field, value)
        return self
