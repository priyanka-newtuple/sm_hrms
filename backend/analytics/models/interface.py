"""Internal constants for usage analytics."""

from __future__ import annotations

from common.data_model import ExtendedStrEnum


class AnalyticsGroupBy(ExtendedStrEnum):
    """Allowed, SQL-safe dimensions for the flexible analytics report."""

    DAY = "day"
    WEEK = "week"
    USER = "user"
    ACTION = "action"
    CATEGORY = "category"


GROUP_BY_LABELS: dict[AnalyticsGroupBy, str] = {
    AnalyticsGroupBy.DAY: "Day",
    AnalyticsGroupBy.WEEK: "Week",
    AnalyticsGroupBy.USER: "User",
    AnalyticsGroupBy.ACTION: "Action",
    AnalyticsGroupBy.CATEGORY: "Category",
}


LOGIN_EVENT_TYPES: tuple[str, ...] = (
    "AUTH_LOGIN_SUCCESS",
    "AUTH_GOOGLE_LOGIN",
)
