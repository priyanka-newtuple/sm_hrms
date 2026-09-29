from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PolicyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=2, max_length=200)
    category: str = Field(min_length=2, max_length=60)
    summary: str = Field(min_length=2, max_length=2000)
    body: str = Field(min_length=2)
    owner: str = Field(default="People", max_length=100)
    version: str = Field(default="1.0", max_length=30)
    effective_date: date
    review_date: date | None = None
    visibility: str = "public"


class LearningEventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=2, max_length=200)
    description: str | None = None
    category: str = Field(min_length=2, max_length=40)
    starts_at: datetime
    ends_at: datetime
    location: str = Field(min_length=2, max_length=200)
    audience: str = Field(default="All employees", max_length=200)
    capacity: int | None = Field(default=None, gt=0)
    registration_url: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def dates_are_ordered(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("End time must be after start time")
        return self


class JobDescriptionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=2, max_length=200)
    department: str = Field(min_length=2, max_length=100)
    level: str = Field(min_length=1, max_length=60)
    responsibilities: str = Field(min_length=2)
    requirements: str = Field(min_length=2)
    preferred_skills: str | None = None
    experience: str | None = Field(default=None, max_length=100)
    employment_type: str = Field(default="Full-time", max_length=50)


class JobOpeningIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_description_id: UUID
    requisition_code: str = Field(min_length=2, max_length=40)
    hiring_manager_id: UUID
    openings: int = Field(default=1, gt=0, le=100)
    location: str = Field(min_length=2, max_length=150)
    work_mode: str = Field(min_length=2, max_length=30)
    application_deadline: date
    referral_bonus: str | None = Field(default=None, max_length=100)


class ReferralIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_name: str = Field(min_length=2, max_length=200)
    candidate_email: str = Field(min_length=5, max_length=255)
    candidate_phone: str | None = Field(default=None, max_length=50)
    message: str | None = Field(default=None, max_length=3000)


class HolidayContentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    holiday_date: date
    name: str = Field(min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    is_optional: bool = False
    location: str = Field(default="All locations", max_length=100)


class DecisionIn(BaseModel):
    decision: str
    comment: str | None = Field(default=None, max_length=2000)
