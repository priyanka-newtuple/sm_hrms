"""Communications REST controller module."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Request, status

from common.auth import require_permission
from common.logger import logger, tracer
from common.utils import raise_http_error
from communications.models.request import NotificationCreateRequest
from communications.models.response import (
    CollaborationStatusResponse,
    NotificationCreateResponse,
)

if TYPE_CHECKING:
    from fastapi.params import Depends as DependsParam

    from auth.manager import AuthServiceManager
    from communications.manager import CommunicationsServiceManager
    from database.manager import DatabaseServiceManager

CommWriteActor = Annotated[dict[str, object], Depends(require_permission("notification", "write"))]


class CommunicationsRestController:
    """Implements communications REST controller."""

    def __init__(
        self,
        communications_service_manager: CommunicationsServiceManager,
        database_service_manager: DatabaseServiceManager | None = None,
        auth_service_manager: AuthServiceManager | None = None,
    ) -> None:
        self.communications_service_manager = communications_service_manager
        self.manager = communications_service_manager
        self.database_service_manager = database_service_manager
        self.current_db = (
            database_service_manager.postgres_db_service()
            if database_service_manager and hasattr(database_service_manager, "postgres_db_service")
            else None
        )
        self.current_db_engine = getattr(self.current_db, "engine", None)
        self.auth_service_manager = auth_service_manager

    @staticmethod
    def _route_dependencies(security: DependsParam | None) -> list[DependsParam] | None:
        return [security] if security else None

    @staticmethod
    def _error_context(request_id: str, operation: str) -> dict[str, str]:
        return {
            "request_id": request_id,
            "controller": "CommunicationsRestController",
            "operation": operation,
        }

    def prepare(self, app: APIRouter, security: DependsParam | None = None) -> None:
        """Prepare the communications REST controller."""
        route_dependencies = self._route_dependencies(security)

        @app.get(
            "/communications/status",
            status_code=status.HTTP_200_OK,
            tags=["communications"],
            response_model=CollaborationStatusResponse,
            dependencies=route_dependencies,
        )
        def status_endpoint(request: Request):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("CommunicationsController.status"):
                try:
                    logger.info("communications status requested", extra={"request_id": request_id})
                    return self.communications_service_manager.get_status()
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "status"))

        @app.get(
            "/collaboration/status",
            status_code=status.HTTP_200_OK,
            tags=["collaboration"],
            response_model=CollaborationStatusResponse,
            dependencies=route_dependencies,
        )
        def legacy_status_endpoint(request: Request):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("CommunicationsController.legacy_status"):
                try:
                    logger.info("collaboration status requested", extra={"request_id": request_id})
                    return self.communications_service_manager.get_status()
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "legacy_status"))

        @app.post(
            "/communications/notifications",
            status_code=status.HTTP_201_CREATED,
            tags=["communications"],
            response_model=NotificationCreateResponse,
            dependencies=route_dependencies,
        )
        def create_notification_endpoint(
            request: Request,
            notification_request: NotificationCreateRequest,
            actor: CommWriteActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("CommunicationsController.create_notification"):
                try:
                    logger.info(
                        "communications create_notification", extra={"request_id": request_id}
                    )
                    return self.communications_service_manager.create_notification_for_actor(
                        actor,
                        notification_request,
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "create_notification"))

        @app.post(
            "/collaboration/notifications",
            status_code=status.HTTP_201_CREATED,
            tags=["collaboration"],
            response_model=NotificationCreateResponse,
            dependencies=route_dependencies,
        )
        def legacy_create_notification_endpoint(
            request: Request,
            notification_request: NotificationCreateRequest,
            actor: CommWriteActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span(
                "CommunicationsController.legacy_create_notification"
            ):
                try:
                    logger.info(
                        "collaboration create_notification", extra={"request_id": request_id}
                    )
                    return self.communications_service_manager.create_notification_for_actor(
                        actor,
                        notification_request,
                    )
                except Exception as exc:
                    raise_http_error(
                        exc,
                        self._error_context(request_id, "legacy_create_notification"),
                    )
