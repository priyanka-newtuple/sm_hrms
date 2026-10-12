"""Native HRMS route responses."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class LeaveCreateResponse(BaseModel):
    entity_id: str
    identifier: str
    state: str
    idempotent: bool = False


class LeaveListItem(BaseModel):
    custom: dict[str, Any] = {}  # fields the organization added in Settings
    entity_id: str
    identifier: str
    employee_name: str
    start_date: str
    end_date: str
    leave_type: str
    reason: str | None = None
    days: int = 0  # Working days: weekdays that are not published holidays.
    state: str


class EmployeeListItem(BaseModel):
    custom: dict[str, Any] = {}  # fields the organization added in Settings
    entity_id: str
    employee_code: str
    full_name: str
    work_email: str
    department: str
    designation: str
    reports_to_name: str | None = None
    employment_status: str
    role: str
    account_status: str = "not_linked"
    onboarding_state: str = "not_started"
    can_setup_access: bool = False
    uses_google_sign_in: bool = False
    # Editable details, so the edit form starts from what is saved.
    reports_to_entity_id: str | None = None
    date_joined: str | None = None
    employment_type: str | None = None
    work_location: str | None = None
    notice_period_days: int | None = None
    phone: str | None = None
    # Exit: an active employee with a future last working day is serving notice.
    last_working_day: str | None = None
    exit_reason: str | None = None
    on_notice: bool = False


class EmployeeCreateResponse(BaseModel):
    employee: EmployeeListItem
    onboarding_entity_id: str
    onboarding_state: str
    onboarding_task_count: int
    account_status: str = "pending"
    idempotent: bool = False


class OnboardingStepItem(BaseModel):
    sequence: int
    task_id: str | None = None
    title: str
    status: str
    readiness: str
    owner_name: str
    owner_role: str
    due_date: datetime | None = None
    depends_on: list[int]
    can_complete: bool = False
    assigned_to_me: bool = False  # Owned by the reader; HR may complete others' steps too.
    can_manage: bool = False  # HR may reassign, re-date or skip it.


class OnboardingCaseItem(BaseModel):
    entity_id: str
    identifier: str
    employee_entity_id: str
    employee_name: str
    employee_code: str
    designation: str
    department: str
    state: str
    completed_steps: int
    total_steps: int
    can_complete_case: bool = False
    can_cancel: bool = False
    cancel_reason: str | None = None
    steps: list[OnboardingStepItem]
