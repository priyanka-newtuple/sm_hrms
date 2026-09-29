from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hrms.models.enums import AllocationStatus
from hrms.schemas.common import EmployeeSummary, ProjectSummary


class AllocationConfirmation(BaseModel):
    confirm_overallocation: bool = False
    overallocation_reason: str | None = Field(default=None, max_length=2000)


class AllocationCreate(AllocationConfirmation):
    employee_id: uuid.UUID
    project_id: uuid.UUID
    allocation_percent: float = Field(gt=0, le=100)
    role_on_project: str = Field(min_length=1, max_length=100)
    start_date: date
    end_date: date | None = None
    status: AllocationStatus = AllocationStatus.ACTIVE
    billable: bool = True
    notes: str | None = None
    billing_rate_override: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _end_after_start(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        return self


class AllocationUpdate(AllocationConfirmation):
    allocation_percent: float | None = Field(default=None, gt=0, le=100)
    role_on_project: str | None = Field(default=None, min_length=1, max_length=100)
    start_date: date | None = None
    end_date: date | None = None
    status: AllocationStatus | None = None
    billable: bool | None = None
    notes: str | None = None
    billing_rate_override: float | None = Field(default=None, ge=0)


class AllocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    employee: EmployeeSummary | None = None
    project_id: uuid.UUID
    project: ProjectSummary | None = None
    allocation_percent: float
    role_on_project: str
    start_date: date
    end_date: date | None = None
    status: AllocationStatus
    billable: bool
    notes: str | None = None
    over_allocated: bool = False
    total_allocation_percent: float = 0
    overallocated_periods: list[dict] = []
    allocated_by_id: uuid.UUID | None = None
    # Commercial — stripped without VIEW_BILLING_RATE
    billing_rate_override: float | None = None


class CapacityConflict(BaseModel):
    """One allocation already competing for the same days."""

    allocation_id: uuid.UUID
    project_name: str
    allocation_percent: float
    start_date: date
    end_date: date | None = None


class AllocationWriteResult(BaseModel):
    """
    Wraps the saved allocation with a capacity verdict.

    Over-allocation is reported, not refused: brief overlaps are legitimate during
    handovers, so the API saves the row and lets the UI surface an amber warning.
    """

    allocation: AllocationOut
    over_allocated: bool = False
    total_allocation_percent: float = 0
    conflicts: list[CapacityConflict] = []


class CapacityOut(BaseModel):
    """Committed vs available capacity for one employee on a given date."""

    employee_id: uuid.UUID
    on_date: date
    total_allocation_percent: float
    available_percent: float
    over_allocated: bool
    allocations: list[CapacityConflict] = []


class AllocationPreview(BaseModel):
    employee_id: uuid.UUID
    project_id: uuid.UUID
    start_date: date
    end_date: date | None = None
    allocation_percent: float = Field(gt=0, le=100)
    exclude_allocation_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def dates(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        return self
