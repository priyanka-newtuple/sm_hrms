from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hrms.models.enums import (
    CustomerStatus,
    EngagementType,
    ProjectHealth,
    ProjectStatus,
)
from hrms.schemas.common import CustomerSummary, EmployeeSummary


class _DateRangeCheck(BaseModel):
    @model_validator(mode="after")
    def _end_after_start(self):
        start = getattr(self, "start_date", None) or getattr(self, "contract_start_date", None)
        end = getattr(self, "end_date", None) or getattr(self, "contract_end_date", None)
        if start and end and end < start:
            raise ValueError("end date cannot be before start date")
        return self


# --------------------------------------------------------------------------- customers


class CustomerCreate(_DateRangeCheck):
    name: str = Field(min_length=1, max_length=200)
    industry: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    account_owner_id: uuid.UUID | None = None
    status: CustomerStatus = CustomerStatus.ACTIVE
    contract_start_date: date | None = None
    contract_end_date: date | None = None
    currency: str = Field(default="INR", min_length=3, max_length=3)
    payment_terms_days: int | None = Field(default=None, ge=0, le=365)
    billing_address: str | None = None
    country: str | None = None
    notes: str | None = None
    contract_value: float | None = Field(default=None, ge=0)


class CustomerUpdate(_DateRangeCheck):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    industry: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    account_owner_id: uuid.UUID | None = None
    status: CustomerStatus | None = None
    contract_start_date: date | None = None
    contract_end_date: date | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    payment_terms_days: int | None = Field(default=None, ge=0, le=365)
    billing_address: str | None = None
    country: str | None = None
    notes: str | None = None
    contract_value: float | None = Field(default=None, ge=0)


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    status: CustomerStatus
    industry: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    account_owner_id: uuid.UUID | None = None
    account_owner: EmployeeSummary | None = None
    contract_start_date: date | None = None
    contract_end_date: date | None = None
    currency: str
    country: str | None = None
    billing_address: str | None = None
    notes: str | None = None
    project_count: int | None = None
    # Commercial — stripped without VIEW_CUSTOMER_CONTRACT_VALUE
    contract_value: float | None = None
    payment_terms_days: int | None = None


# --------------------------------------------------------------------------- projects


class ProjectCreate(_DateRangeCheck):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    customer_id: uuid.UUID
    project_manager_id: uuid.UUID
    delivery_manager_id: uuid.UUID | None = None
    status: ProjectStatus = ProjectStatus.PLANNED
    start_date: date
    end_date: date | None = None
    description: str | None = None
    engagement_type: EngagementType = EngagementType.TIME_AND_MATERIALS
    health: ProjectHealth = ProjectHealth.GREEN
    currency: str = Field(default="INR", min_length=3, max_length=3)
    practice: str | None = None
    budgeted_hours: int | None = Field(default=None, ge=0)
    budget_amount: float | None = Field(default=None, ge=0)
    billing_rate: float | None = Field(default=None, ge=0)
    revenue: float | None = Field(default=None, ge=0)
    margin_percent: float | None = Field(default=None, ge=-100, le=100)


class ProjectUpdate(_DateRangeCheck):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    customer_id: uuid.UUID | None = None
    project_manager_id: uuid.UUID | None = None
    delivery_manager_id: uuid.UUID | None = None
    status: ProjectStatus | None = None
    start_date: date | None = None
    end_date: date | None = None
    description: str | None = None
    engagement_type: EngagementType | None = None
    health: ProjectHealth | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    practice: str | None = None
    budgeted_hours: int | None = Field(default=None, ge=0)
    budget_amount: float | None = Field(default=None, ge=0)
    billing_rate: float | None = Field(default=None, ge=0)
    revenue: float | None = Field(default=None, ge=0)
    margin_percent: float | None = Field(default=None, ge=-100, le=100)


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    approval_status: str = "approved"
    created_by_id: uuid.UUID | None = None
    name: str
    status: ProjectStatus
    customer_id: uuid.UUID
    customer: CustomerSummary | None = None
    project_manager_id: uuid.UUID
    project_manager: EmployeeSummary | None = None
    delivery_manager_id: uuid.UUID | None = None
    delivery_manager: EmployeeSummary | None = None
    start_date: date
    end_date: date | None = None
    description: str | None = None
    engagement_type: EngagementType
    health: ProjectHealth
    currency: str
    practice: str | None = None
    budgeted_hours: int | None = None
    allocated_headcount: int | None = None
    # Commercial — each stripped without its respective VIEW_* permission key
    budget_amount: float | None = None
    billing_rate: float | None = None
    revenue: float | None = None
    margin_percent: float | None = None
