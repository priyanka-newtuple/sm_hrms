"""Business logic for organization usage analytics."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any

from analytics.models.interface import GROUP_BY_LABELS
from analytics.models.response import (
    ActionBreakdownItem,
    ActionBreakdownResponse,
    AnalyticsColumn,
    AnalyticsFlexibleResponse,
    AnalyticsOverviewResponse,
    AnalyticsSeriesPoint,
    AnalyticsStatusResponse,
    LoginActivityResponse,
    UserActivityItem,
    UserActivityResponse,
)
from common.auth import actor_str
from common.enums import ModuleStatus
from common.logger import logger
from exceptions import ServiceError, ValidationError

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from analytics.db_models import AnalyticsModelService
    from analytics.models.request import AnalyticsFlexibleRequest


# Default lookback (inclusive) when no date_from is supplied — last 30 days.
DEFAULT_ANALYTICS_RANGE_DAYS = 29


class AnalyticsServiceManager:
    """Validates ranges and exposes tenant-scoped analytics reports."""

    def __init__(
        self,
        db_model_service: AnalyticsModelService,
        user_model_service: Any,
        audit_events_model_service: Any,
    ) -> None:
        """Initialize analytics with injected database, user, and audit services."""
        self.db = db_model_service
        self.users = user_model_service
        self.audit_events = audit_events_model_service
        self.module_name = "analytics"
        self._started = False

    def start(self) -> None:
        """Mark the analytics module as started for lifecycle reporting."""
        self._started = True

    def stop(self) -> None:
        """Mark the analytics module as stopped during application shutdown."""
        self._started = False

    def get_status(self) -> AnalyticsStatusResponse:
        """Build the public lifecycle status response for this module."""
        return AnalyticsStatusResponse(
            module=self.module_name,
            status=ModuleStatus.READY.value,
            started=self._started,
        )

    def _organization_id(self, actor: dict[str, object]) -> str:
        """Read the tenant ID from the authenticated actor or reject the request."""
        organization_id = actor_str(actor, "organization_id")
        if not organization_id:
            raise ValidationError("actor organization_id is required")
        return organization_id

    def _range(
        self, date_from: date | None, date_to: date | None
    ) -> tuple[date, date, datetime, datetime]:
        """Validate dates and convert the inclusive range to a UTC query window."""
        end = date_to or datetime.now(UTC).date()
        start = date_from or (end - timedelta(days=DEFAULT_ANALYTICS_RANGE_DAYS))
        if start > end:
            raise ValidationError("date_from must be on or before date_to")
        start_at = datetime.combine(start, time.min, tzinfo=UTC)
        end_at = datetime.combine(end + timedelta(days=1), time.min, tzinfo=UTC)
        return start, end, start_at, end_at

    @staticmethod
    def _points(
        rows: list[tuple[Any, int]], start: date, end: date, *, weekly: bool = False
    ) -> list[AnalyticsSeriesPoint]:
        """Convert time buckets into a complete series, including zero-count gaps."""
        counts = {
            bucket.date().isoformat() if isinstance(bucket, datetime) else str(bucket): int(count)
            for bucket, count in rows
        }
        current = start - timedelta(days=start.weekday()) if weekly else start
        step = timedelta(days=7 if weekly else 1)
        points: list[AnalyticsSeriesPoint] = []
        while current <= end:
            label = current.isoformat()
            points.append(AnalyticsSeriesPoint(label=label, value=counts.get(label, 0)))
            current += step
        return points

    def login_activity(
        self, db: Session, actor: dict[str, object], date_from: date | None, date_to: date | None
    ) -> LoginActivityResponse:
        """Build the tenant-scoped successful-login report for a date range."""
        organization_id = self._organization_id(actor)
        start, end, start_at, end_at = self._range(date_from, date_to)
        try:
            result = self.db.login_activity(
                db,
                organization_id,
                start_at,
                end_at,
                audit_model_service=self.audit_events,
            )
            return LoginActivityResponse(
                date_from=start,
                date_to=end,
                active_users=result["active_users"],
                total_logins=result["total_logins"],
                daily=self._points(result["daily"], start, end),
                weekly=self._points(result["weekly"], start, end, weekly=True),
            )
        except Exception as exc:
            logger.exception(f"Analytics login report failed for org {organization_id} from {start} to {end}: {exc}")  # fmt: skip
            raise ServiceError("Unable to load login analytics") from exc

    def action_breakdown(
        self, db: Session, actor: dict[str, object], date_from: date | None, date_to: date | None
    ) -> ActionBreakdownResponse:
        """Build the tenant-scoped non-authentication action report."""
        organization_id = self._organization_id(actor)
        start, end, start_at, end_at = self._range(date_from, date_to)
        try:
            items = [
                ActionBreakdownItem(**item)
                for item in self.db.action_breakdown(
                    db,
                    organization_id,
                    start_at,
                    end_at,
                    audit_model_service=self.audit_events,
                )
            ]
            return ActionBreakdownResponse(
                date_from=start,
                date_to=end,
                total_actions=sum(item.count for item in items),
                items=items,
            )
        except Exception as exc:
            logger.exception(f"Analytics action report failed for org {organization_id} from {start} to {end}: {exc}")  # fmt: skip
            raise ServiceError("Unable to load action analytics") from exc

    def overview(
        self,
        db: Session,
        actor: dict[str, object],
        date_from: date | None,
        date_to: date | None,
        *,
        user_limit: int,
        user_offset: int,
    ) -> AnalyticsOverviewResponse:
        """Return all fixed reports in one response for the analytics page."""
        return AnalyticsOverviewResponse(
            logins=self.login_activity(db, actor, date_from, date_to),
            actions=self.action_breakdown(db, actor, date_from, date_to),
            users=self.user_activity(
                db,
                actor,
                date_from,
                date_to,
                limit=user_limit,
                offset=user_offset,
            ),
        )

    def user_activity(
        self,
        db: Session,
        actor: dict[str, object],
        date_from: date | None,
        date_to: date | None,
        *,
        limit: int = 25,
        offset: int = 0,
    ) -> UserActivityResponse:
        """Build one page of per-actor login totals and action counts."""
        organization_id = self._organization_id(actor)
        start, end, start_at, end_at = self._range(date_from, date_to)
        try:
            rows, total = self.db.user_activity(
                db,
                organization_id,
                start_at,
                end_at,
                limit=limit,
                offset=offset,
                audit_model_service=self.audit_events,
                user_model_service=self.users,
            )
            items = [UserActivityItem(**item) for item in rows]
            return UserActivityResponse(
                date_from=start,
                date_to=end,
                total=total,
                limit=limit,
                offset=offset,
                items=items,
            )
        except Exception as exc:
            logger.exception(f"Analytics per-user report failed for org {organization_id} from {start} to {end}: {exc}")  # fmt: skip
            raise ServiceError("Unable to load per-user analytics") from exc

    def flexible(
        self, db: Session, actor: dict[str, object], request: AnalyticsFlexibleRequest
    ) -> AnalyticsFlexibleResponse:
        """Build a custom report from validated groupings and optional filters."""
        organization_id = self._organization_id(actor)
        start, end, start_at, end_at = self._range(request.date_from, request.date_to)
        try:
            rows, total = self.db.flexible(
                db,
                organization_id,
                start_at,
                end_at,
                group_by=request.group_by,
                include_auth=request.include_auth,
                event_type=request.event_type,
                user_id=request.user_id,
                limit=request.limit,
                offset=request.offset,
                audit_model_service=self.audit_events,
                user_model_service=self.users,
            )
            columns = [
                AnalyticsColumn(key=dimension.value, label=GROUP_BY_LABELS[dimension])
                for dimension in request.group_by
            ] + [AnalyticsColumn(key="count", label="Count")]
            return AnalyticsFlexibleResponse(
                date_from=start,
                date_to=end,
                columns=columns,
                rows=rows,
                total=total,
                limit=request.limit,
                offset=request.offset,
            )
        except Exception as exc:
            logger.exception(f"Flexible analytics report failed for org {organization_id} from {start} to {end}: {exc}")  # fmt: skip
            raise ServiceError("Unable to load flexible analytics") from exc
