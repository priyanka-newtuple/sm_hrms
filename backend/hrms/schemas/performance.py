from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class CycleIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=4000)
    start_date: date
    end_date: date
    goal_due_date: date
    self_review_due_date: date
    manager_review_due_date: date

    @model_validator(mode="after")
    def validate_dates(self):
        if not (
            self.start_date <= self.goal_due_date <= self.end_date
            and self.start_date <= self.self_review_due_date <= self.end_date
            and self.start_date <= self.manager_review_due_date <= self.end_date
        ):
            raise ValueError("All deadlines must fall inside the review period.")
        if not self.goal_due_date <= self.self_review_due_date <= self.manager_review_due_date:
            raise ValueError("Goal, self-review, and manager deadlines must be chronological.")
        return self


class DecisionIn(BaseModel):
    decision: Literal["approve", "changes_requested"]
    comment: str | None = Field(default=None, max_length=2000)


class GoalIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    category: Literal["delivery", "competency", "leadership", "learning", "organization"]
    measurement: str = Field(min_length=1, max_length=2000)
    weight: int = Field(gt=0, le=100)
    target_date: date
    progress: int = Field(default=0, ge=0, le=100)
    evidence: str | None = Field(default=None, max_length=4000)


class SelfReviewIn(BaseModel):
    summary: str = Field(min_length=1, max_length=8000)
    rating: int = Field(ge=1, le=5)


class ManagerReviewIn(BaseModel):
    summary: str = Field(min_length=1, max_length=8000)
    rating: int = Field(ge=1, le=5)


class CalibrationIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(min_length=1, max_length=4000)


class FeedbackIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    contribution: str = Field(min_length=1, max_length=4000)
    collaboration: str | None = Field(default=None, max_length=4000)


class AcknowledgeIn(BaseModel):
    comment: str | None = Field(default=None, max_length=4000)


class GoalSubmitIn(BaseModel):
    cycle_id: UUID
