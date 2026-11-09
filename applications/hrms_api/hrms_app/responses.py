"""Native HRMS route responses."""

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
    onboarding_state: str | None = None
    onboarding_status_message: str | None = None
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

