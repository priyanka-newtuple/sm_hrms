from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkItem(BaseModel):
    id: UUID
    source: Literal["tasks", "documents", "projects", "performance", "hr_content"]
    kind: Literal["action", "approval"]
    title: str
    description: str | None = None
    employee_name: str
    department: str
    date_joined: date | None = None
    workflow_type: str = "onboarding"
    status: str
    due_date: date | None = None
    overdue: bool = False
    action_type: str
    assignee_name: str | None = None
    note: str | None = None
    can_act: bool = False
    payroll_required: bool = False
    file_name: str | None = None
    can_reassign: bool = False
    record_id: UUID | None = None
    href: str | None = None


class WorkAssetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: UUID
    assigned_date: date
    condition_notes: str | None = Field(default=None, max_length=2000)


class WorkAllocationIn(BaseModel):
    confirm_overallocation: bool = False
    overallocation_reason: str | None = Field(default=None, max_length=2000)
    model_config = ConfigDict(extra="forbid")
    project_id: UUID
    allocation_percent: float = Field(gt=0, le=100)
    role_on_project: str = Field(min_length=1, max_length=100)
    start_date: date
    end_date: date | None = None


class ReassignIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employee_id: UUID
    reason: str = Field(min_length=1, max_length=2000)
