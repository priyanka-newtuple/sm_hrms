from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Action(Contract):
    action: str = Field(min_length=1, max_length=50)
    data: dict = Field(default_factory=dict)
    expected_revision: int = Field(default=0, ge=0)
    idempotency_key: str = Field(min_length=8, max_length=128)


class CustomerInput(Contract):
    name: str = Field(min_length=1, max_length=150)
    contact_name: str = Field(default="", max_length=150)
    contact_email: str = Field(default="", max_length=200)
    currency: str = Field(default="INR", pattern=r"^[A-Z]{3}$")
    contract_value: float = Field(default=0, ge=0, allow_inf_nan=False)


class Dates(Contract):
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def ordered(self):
        if self.end_date < self.start_date:
            raise ValueError("End date must be on or after start date")
        if self.start_date.year < 1900 or self.end_date.year > 2200:
            raise ValueError("Dates must be between 1900 and 2200")
        return self


class ProjectInput(Dates):
    name: str = Field(min_length=1, max_length=150)
    description: str = Field(default="", max_length=4000)
    customer_id: UUID
    pm_id: UUID
    dm_id: UUID
    approver_id: UUID
    engagement_type: Literal["time_material", "fixed_price", "internal"] = (
        "time_material"
    )
    practice: str = Field(default="", max_length=100)
    health: Literal["green", "amber", "red"] = "green"
    currency: str = Field(default="INR", pattern=r"^[A-Z]{3}$")
    budget_amount: float = Field(default=0, ge=0, allow_inf_nan=False)
    billing_rate: float = Field(default=0, ge=0, allow_inf_nan=False)
    planned_hours: float = Field(default=0, ge=0, allow_inf_nan=False)
    note: str = Field(default="", max_length=2000)


class AllocationInput(Dates):
    employee_id: UUID
    project_role_id: str = Field(min_length=1)
    percentage: float = Field(gt=0, le=100, allow_inf_nan=False)
    billable: Literal["yes", "no"] = "yes"
    billing_rate: float = Field(default=0, ge=0, allow_inf_nan=False)
    approver_id: UUID | None = None
    note: str = Field(default="", max_length=2000)


class Comment(Contract):
    comment: str = Field(min_length=1, max_length=2000)


class Release(Contract):
    approver_id: UUID | None = None
    note: str = Field(min_length=1, max_length=2000)
