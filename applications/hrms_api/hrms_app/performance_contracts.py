"""Product input contracts. The platform remains unaware of HR policy."""
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Participant(Contract):
    employee_id: UUID
    calibrator_user_id: UUID


class CycleInput(Contract):
    name: str = Field(min_length=1, max_length=150)
    description: str = Field(default='', max_length=4000)
    start_date: date
    goal_due_date: date
    self_review_due_date: date
    manager_review_due_date: date
    end_date: date
    approver_id: UUID
    participants: list[Participant] = Field(min_length=1, max_length=200)

    @model_validator(mode='after')
    def valid_dates(self):
        if not self.start_date <= self.goal_due_date <= self.self_review_due_date <= self.manager_review_due_date <= self.end_date:
            raise ValueError('Dates must follow start, goals, self review, manager review, end order')
        if len({p.employee_id for p in self.participants}) != len(self.participants):
            raise ValueError('An employee can appear only once per cycle')
        return self


class GoalInput(Contract):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=4000)
    category: Literal['delivery', 'competency', 'leadership', 'learning', 'organization'] = 'delivery'
    measurement: str = Field(min_length=1, max_length=2000)
    weight: int = Field(ge=1, le=100)
    target_date: date
    progress: int = Field(default=0, ge=0, le=100)
    evidence: str = Field(default='', max_length=4000)


class Assessment(Contract):
    summary: str = Field(min_length=1, max_length=8000)
    rating: int = Field(ge=1, le=5)


class Comment(Contract):
    comment: str = Field(min_length=1, max_length=4000)


class Calibration(Comment):
    rating: int = Field(ge=1, le=5)


class FeedbackRequest(Contract):
    project_reference: str = Field(min_length=1, max_length=200)
    reviewer_user_id: UUID


class FeedbackInput(Contract):
    rating: int = Field(ge=1, le=5)
    contribution: str = Field(min_length=1, max_length=4000)
    collaboration: str = Field(default='', max_length=4000)


class Reassignment(Comment):
    manager_user_id: UUID
    calibrator_user_id: UUID


class Action(Contract):
    idempotency_key: str = Field(min_length=8, max_length=128)
    action: str = Field(min_length=1, max_length=40)
    data: dict = Field(default_factory=dict)
