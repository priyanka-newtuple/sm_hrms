"""Usage analytics REST controller module."""

from __future__ import annotations

from datetime import date  # noqa: TC003 - FastAPI resolves this annotation at runtime
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Query, Request

from analytics.models.request import AnalyticsFlexibleRequest
from analytics.models.response import (
    AnalyticsFlexibleResponse,
    AnalyticsOverviewResponse,
    AnalyticsStatusResponse,
)
from common.auth import require_permission
from common.deps import get_db
from common.logger import tracer
from common.utils import raise_http_error

if TYPE_CHECKING:
    from fastapi.params import Depends as DependsParam
    from sqlalchemy.orm import Session

    from analytics.manager import AnalyticsServiceManager

AnalyticsReadActor = Annotated[dict[str, object], Depends(require_permission("analytics", "read"))]


class AnalyticsRestController:
    """REST controller for organization usage analytics."""

    def __init__(
        self,
        analytics_service_manager: AnalyticsServiceManager,
        database_service_manager: object | None = None,
        auth_service_manager: object | None = None,
    ) -> None:
        _ = database_service_manager, auth_service_manager
        self.manager = analytics_service_manager

    @staticmethod
    def _route_dependencies(security: DependsParam | None) -> list[DependsParam] | None:
        return [security] if security else None

    def prepare(self, app: APIRouter, security: DependsParam | None = None) -> None:
        """Register all analytics routes on the given router."""
        route_dependencies = self._route_dependencies(security)

        @app.get(
            "/analytics/status",
            response_model=AnalyticsStatusResponse,
            tags=["analytics"],
            dependencies=route_dependencies,
        )
        def get_status() -> AnalyticsStatusResponse:
            """Return the analytics module lifecycle status."""
            return self.manager.get_status()

        @app.get(
            "/analytics/overview",
            response_model=AnalyticsOverviewResponse,
            tags=["analytics"],
            dependencies=route_dependencies,
        )
        def get_overview(
            request: Request,
            actor: AnalyticsReadActor,
            db: Session = Depends(get_db),
            date_from: date | None = Query(default=None),
            date_to: date | None = Query(default=None),
            user_limit: int = Query(default=25, ge=1, le=100),
            user_offset: int = Query(default=0, ge=0),
        ) -> AnalyticsOverviewResponse:
            """Return fixed analytics reports and one page of user activity."""
            request_id = getattr(request.state, "request_id", "")
            with tracer.start_as_current_span("AnalyticsRestController.get_overview"):
                try:
                    return self.manager.overview(
                        db,
                        actor,
                        date_from,
                        date_to,
                        user_limit=user_limit,
                        user_offset=user_offset,
                    )
                except Exception as exc:
                    raise_http_error(
                        exc,
                        {"request_id": request_id, "operation": "get_overview"},
                    )

        @app.post(
            "/analytics/flexible",
            response_model=AnalyticsFlexibleResponse,
            tags=["analytics"],
            dependencies=route_dependencies,
        )
        def run_flexible_report(
            request: Request,
            payload: AnalyticsFlexibleRequest,
            actor: AnalyticsReadActor,
            db: Session = Depends(get_db),
        ) -> AnalyticsFlexibleResponse:
            """Return one page of a user-configured grouped report."""
            request_id = getattr(request.state, "request_id", "")
            with tracer.start_as_current_span("AnalyticsRestController.run_flexible_report"):
                try:
                    return self.manager.flexible(db, actor, payload)
                except Exception as exc:
                    raise_http_error(
                        exc,
                        {"request_id": request_id, "operation": "run_flexible_report"},
                    )
