from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from hrms.models.enums import EmploymentStatus, EmploymentType, ExitType
from hrms.schemas.common import EmployeeSummary, RoleSummary

# Re-exported for callers that already import RoleOut from here.
RoleOut = RoleSummary


class EmployeeCreate(BaseModel):
    email: EmailStr  # becomes both the login identity and work_email
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    department: str = Field(min_length=1, max_length=100)
    designation: str = Field(min_length=1, max_length=100)
    role_id: uuid.UUID
    reports_to_id: uuid.UUID | None = None
    date_joined: date
    employment_type: EmploymentType = EmploymentType.FULL_TIME
    work_location: str | None = None
    probation_end_date: date | None = None
    notice_period_days: int | None = Field(default=None, ge=0, le=365)
    phone: str | None = None


class EmployeeUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    department: str | None = None
    designation: str | None = None
    role_id: uuid.UUID | None = None
    reports_to_id: uuid.UUID | None = None
    employment_status: EmploymentStatus | None = None
    employment_type: EmploymentType | None = None
    work_location: str | None = None
    probation_end_date: date | None = None
    confirmation_date: date | None = None
    notice_period_days: int | None = Field(default=None, ge=0, le=365)
    phone: str | None = None
    skills: str | None = None
    personal_email: str | None = None
    date_of_birth: date | None = None
    address: str | None = None
    salary_ctc: float | None = Field(default=None, ge=0)
    bank_account_number: str | None = None
    bank_ifsc: str | None = None
    employee_cost_rate: float | None = Field(default=None, ge=0)


class EmployeeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_code: str
    first_name: str
    last_name: str
    full_name: str
    work_email: str
    department: str
    designation: str
    employment_status: EmploymentStatus
    employment_type: EmploymentType
    date_joined: date
    work_location: str | None = None
    probation_end_date: date | None = None
    confirmation_date: date | None = None
    notice_period_days: int | None = None
    reports_to_id: uuid.UUID | None = None
    reports_to: EmployeeSummary | None = None
    role_id: uuid.UUID
    role: RoleSummary
    phone: str | None = None
    skills: str | None = None

    # Offboarding
    last_working_day: date | None = None
    exit_type: ExitType | None = None
    exit_reason: str | None = None
    rehire_eligible: bool | None = None

    # Sensitive — present on the model but stripped by
    # app.authz.serializers.strip_employee_fields before the response leaves the API.
    personal_email: str | None = None
    date_of_birth: date | None = None
    address: str | None = None
    salary_ctc: float | None = None
    bank_account_number: str | None = None
    bank_ifsc: str | None = None
    payroll_reference: str | None = None
    employee_cost_rate: float | None = None


class OffboardRequest(BaseModel):
    last_working_day: date
    exit_type: ExitType
    exit_reason: str | None = None
    rehire_eligible: bool = True


class OffboardingBlocker(BaseModel):
    """One thing standing between this employee and a clean exit."""

    kind: str  # managed_projects | direct_reports | unreturned_assets | open_timesheets
    message: str
    items: list[dict] = []


class OffboardingReadiness(BaseModel):
    employee_id: uuid.UUID
    ready: bool
    blockers: list[OffboardingBlocker] = []
