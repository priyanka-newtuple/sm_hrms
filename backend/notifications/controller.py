"""Notifications REST controller module."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from common.auth import build_actor_context
from common.deps import get_db
from common.logger import logger, tracer
from common.utils import raise_http_error
from notifications.models.response import (
    MarkAllReadResponse,
    NotificationListResponse,
    NotificationRead,
    UnreadCountResponse,
)

if TYPE_CHECKING:
    from fastapi.params import Depends as DependsParam
    from sqlalchemy.orm import Session

    from auth.manager import AuthServiceManager
    from database.manager import DatabaseServiceManager
    from notifications.manager import NotificationsServiceManager

AnyActor = Annotated[dict[str, object], Depends(build_actor_context)]


class NotificationsRestController:
    """Implements notifications REST controller."""

    def __init__(
        self,
        notifications_service_manager: NotificationsServiceManager,
        database_service_manager: DatabaseServiceManager | None = None,
        auth_service_manager: AuthServiceManager | None = None,
    ) -> None:
        _ = database_service_manager, auth_service_manager
        self.manager = notifications_service_manager
        self.notifications_service_manager = notifications_service_manager

    @staticmethod
    def _route_dependencies(security: DependsParam | None) -> list[DependsParam] | None:
        return [security] if security else None

    @staticmethod
    def _error_context(request_id: str, operation: str) -> dict[str, str]:
        return {
            "request_id": request_id,
            "controller": "NotificationsRestController",
            "operation": operation,
        }

    def prepare(self, app: APIRouter, security: DependsParam | None = None) -> None:
        """Prepare the notifications REST controller."""
        route_dependencies = self._route_dependencies(security)

        @app.get(
            "/notifications/unread-count",
            status_code=status.HTTP_200_OK,
            response_model=UnreadCountResponse,
            tags=["notifications"],
            dependencies=route_dependencies,
        )
        def unread_count_endpoint(
            request: Request,
            actor: AnyActor,
            db: Session = Depends(get_db),
        ) -> UnreadCountResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("NotificationsController.unread_count"):
                try:
                    logger.info(
                        "notifications unread-count requested", extra={"request_id": request_id}
                    )
                    return self.manager.get_unread_count_for_actor(actor, db=db)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "unread_count"))

        @app.post(
            "/notifications/{notification_id}/read",
            status_code=status.HTTP_200_OK,
            response_model=NotificationRead,
            tags=["notifications"],
            dependencies=route_dependencies,
        )
        def mark_as_read_endpoint(
            request: Request,
            notification_id: str,
            actor: AnyActor,
            db: Session = Depends(get_db),
        ) -> NotificationRead:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("NotificationsController.mark_as_read"):
                try:
                    logger.info(
                        "notifications mark-as-read requested",
                        extra={"request_id": request_id},
                    )
                    return self.manager.mark_as_read_for_actor(
                        actor, db=db, notification_id=notification_id
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "mark_as_read"))

        @app.post(
            "/notifications/mark-all-read",
            status_code=status.HTTP_200_OK,
            response_model=MarkAllReadResponse,
            tags=["notifications"],
            dependencies=route_dependencies,
        )
        def mark_all_read_endpoint(
            request: Request,
            actor: AnyActor,
            db: Session = Depends(get_db),
        ) -> MarkAllReadResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("NotificationsController.mark_all_read"):
                try:
                    logger.info(
                        "notifications mark-all-read requested",
                        extra={"request_id": request_id},
                    )
                    return self.manager.mark_all_as_read_for_actor(actor, db=db)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "mark_all_read"))

        @app.delete(
            "/notifications/{notification_id}",
            status_code=status.HTTP_204_NO_CONTENT,
            tags=["notifications"],
            dependencies=route_dependencies,
        )
        def delete_notification_endpoint(
            request: Request,
            notification_id: str,
            actor: AnyActor,
            db: Session = Depends(get_db),
        ) -> None:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("NotificationsController.delete"):
                try:
                    logger.info("notifications delete requested", extra={"request_id": request_id})
                    self.manager.delete_notification_for_actor(
                        actor, db=db, notification_id=notification_id
                    )
                    return None
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "delete"))

        @app.get(
            "/notifications",
            status_code=status.HTTP_200_OK,
            response_model=NotificationListResponse,
            tags=["notifications"],
            dependencies=route_dependencies,
        )
        def list_notifications_endpoint_router(
            request: Request,
            actor: AnyActor,
            db: Session = Depends(get_db),
            is_read: bool | None = Query(default=None, description="Filter by read status"),
            limit: int = Query(default=50, le=100, description="Maximum results"),
            offset: int = Query(default=0, ge=0, description="Number to skip"),
        ) -> NotificationListResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("NotificationsController.list"):
                try:
                    logger.info(
                        "notifications list requested",
                        extra={"request_id": request_id},
                    )
                    return self.manager.list_notifications_for_actor(
                        actor,
                        db=db,
                        is_read=is_read,
                        limit=limit,
                        offset=offset,
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "list"))
