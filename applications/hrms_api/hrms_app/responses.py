"""Native HRMS route responses."""

from datetime import datetime

from pydantic import BaseModel


class LeaveCreateResponse(BaseModel):
    entity_id: str
    identifier: str
    state: str
    idempotent: bool = False


class LeaveListItem(BaseModel):
    entity_id: str
    identifier: str
    employee_name: str
    start_date: str
    end_date: str
    leave_type: str
    reason: str | None = None
    state: str


class EmployeeListItem(BaseModel):
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
    steps: list[OnboardingStepItem]
