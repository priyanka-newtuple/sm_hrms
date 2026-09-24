"""Response contracts for usage analytics."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import Field

from common.data_model import BaseModel as PydanticBaseModel


class AnalyticsStatusResponse(PydanticBaseModel):
    """Lifecycle state returned by the analytics status endpoint."""

    module: str
    status: str
    started: bool


class AnalyticsSeriesPoint(PydanticBaseModel):
    """One labeled numeric point used by analytics charts."""

    label: str
    value: int


class LoginActivityResponse(PydanticBaseModel):
    """Successful-login totals and time-series data for a date range."""

    date_from: date
    date_to: date
    active_users: int
    total_logins: int
    daily: list[AnalyticsSeriesPoint] = Field(default_factory=list)
    weekly: list[AnalyticsSeriesPoint] = Field(default_factory=list)


class ActionBreakdownItem(PydanticBaseModel):
    """Count for one action type within one audit category."""

    action: str
    category: str
    count: int


class ActionBreakdownResponse(PydanticBaseModel):
    """Overall non-authentication action totals and their breakdown."""

    date_from: date
    date_to: date
    total_actions: int
    items: list[ActionBreakdownItem] = Field(default_factory=list)


class UserActivityItem(PydanticBaseModel):
    """Login and action summary for one user or system actor."""

    user_id: str
    name: str
    email: str | None = None
    actor_type: str = "user"
    last_login_at: datetime | None = None
    login_count: int
    total_actions: int
    actions: list[ActionBreakdownItem] = Field(default_factory=list)


class UserActivityResponse(PydanticBaseModel):
    """Per-actor activity summaries for the requested date range."""

    date_from: date
    date_to: date
    total: int
    limit: int
    offset: int
    items: list[UserActivityItem] = Field(default_factory=list)


class AnalyticsOverviewResponse(PydanticBaseModel):
    """Fixed analytics reports returned to the page in one response."""

    logins: LoginActivityResponse
    actions: ActionBreakdownResponse
    users: UserActivityResponse


class AnalyticsColumn(PydanticBaseModel):
    """Column metadata used to render a flexible report table."""

    key: str
    label: str


class AnalyticsFlexibleResponse(PydanticBaseModel):
    """Columns and grouped result rows from a flexible analytics query."""

    date_from: date
    date_to: date
    columns: list[AnalyticsColumn]
    rows: list[dict[str, Any]] = Field(default_factory=list)
    total: int
    limit: int
    offset: int
