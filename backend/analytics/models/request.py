"""Request contracts for usage analytics."""

from __future__ import annotations

from datetime import date

from pydantic import Field, model_validator

from analytics.models.interface import AnalyticsGroupBy
from common.data_model import BaseModel as PydanticBaseModel


class AnalyticsFlexibleRequest(PydanticBaseModel):
    """Safe dimensions and filters for the flexible usage report."""

    date_from: date | None = None
    date_to: date | None = None
    group_by: list[AnalyticsGroupBy] = Field(
        default_factory=lambda: [AnalyticsGroupBy.DAY], min_length=1, max_length=3
    )
    include_auth: bool = False
    event_type: str | None = Field(default=None, max_length=128)
    user_id: str | None = Field(default=None, max_length=36)
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_dimensions(self):
        """Reject repeated groupings and normalize optional text filters."""
        if len(set(self.group_by)) != len(self.group_by):
            raise ValueError("group_by dimensions must be unique")
        self.event_type = self.event_type.strip() if self.event_type else None
        self.user_id = self.user_id.strip() if self.user_id else None
        return self
