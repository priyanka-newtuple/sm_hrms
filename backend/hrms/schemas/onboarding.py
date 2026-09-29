from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from hrms.models.enums import (
    DocumentStatus,
    DocumentType,
    InvitationStatus,
    OnboardingStatus,
    OnboardingType,
    TaskActionType,
    TaskStatus,
)


class OnboardingStart(BaseModel):
    employee_id: uuid.UUID
    workflow_type: OnboardingType


class OnboardingEmployeeOut(BaseModel):
    """Enough about the person for the pipeline board without a second API call."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    department: str
    designation: str
    work_email: str
    date_joined: date


class OnboardingTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    seq: int
    step_key: str | None
    title: str
    description: str | None
    status: TaskStatus
    action_type: TaskActionType
    is_complete: bool
    due_date: date | None
    depends_on_seqs: list[int] | None
    assignee_employee_id: uuid.UUID | None
    assignee_role: str | None
    assignee_name: str | None = None
    completed_at: datetime | None
    completed_by_name: str | None = None
    completion_note: str | None
    linked_entity_type: str | None
    linked_entity_id: uuid.UUID | None


class OnboardingRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    workflow_type: OnboardingType
    status: OnboardingStatus
    flowtuple_workflow_id: str | None
    embed_url: str | None = None
    started_at: datetime | None
    completed_at: datetime | None
    tasks: list[OnboardingTaskOut] = []
    employee: OnboardingEmployeeOut | None = None
    progress_done: int = 0
    progress_total: int = 0
    # First READY task — what the pipeline board shows as "waiting on".
    current_task_title: str | None = None
    current_assignee_name: str | None = None
    current_due_date: date | None = None


class EmployeeDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    doc_type: DocumentType
    file_name: str
    content_type: str | None
    size_bytes: int | None
    status: DocumentStatus
    note: str | None
    created_at: datetime
    verified_at: datetime | None
    verified_by_name: str | None = None


class InvitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    status: InvitationStatus
    expires_at: datetime
    accepted_at: datetime | None


class OnboardingDetailOut(OnboardingRecordOut):
    documents: list[EmployeeDocumentOut] = []
    invitation: InvitationOut | None = None


class TaskCompleteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str | None = Field(default=None, max_length=2000)
    # Only meaningful on the Razorpay step — written to employees.payroll_reference.
    payroll_reference: str | None = Field(default=None, max_length=100)


class TaskSkipIn(BaseModel):
    note: str | None = None


class MyActionOut(BaseModel):
    """One actionable step for the current user, across all hires."""

    record_id: uuid.UUID
    task: OnboardingTaskOut
    employee: OnboardingEmployeeOut
    workflow_type: OnboardingType
    overdue: bool


class AcceptInvitationIn(BaseModel):
    token: str


class WizardProfileIn(BaseModel):
    """Self-service fields the new hire fills in the /welcome wizard. Bank fields
    are deliberately allowed here (unlike generic self-service employee edits):
    entering your own payroll account is the point of this step."""

    phone: str | None = None
    personal_email: str | None = None
    date_of_birth: date | None = None
    address: str | None = None
    bank_account_number: str | None = None
    bank_ifsc: str | None = None


class DocumentReviewIn(BaseModel):
    status: DocumentStatus  # verified | rejected
    note: str | None = None
