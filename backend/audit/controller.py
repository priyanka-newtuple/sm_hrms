"""Unified audit events REST controller."""

from __future__ import annotations

from datetime import date  # noqa: TC003 - FastAPI resolves this annotation at runtime
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Query, Request

from common.auth import require_permission
from common.enums import AuditMetadataType
from common.logger import logger, tracer
from common.utils import raise_http_error
from audit.models.interface import LOGS_EVENT_TYPES
from audit.models.response import AuditConstantsResponse, AuditEventListResponse

if TYPE_CHECKING:
    from fastapi.params import Depends as DependsParam

    from audit.manager import AuditServiceManager

AuditReadActor = Annotated[dict[str, object], Depends(require_permission("entity_record", "read"))]
LogsReadActor = Annotated[dict[str, object], Depends(require_permission("logs", "read"))]


class AuditRestController:
    """REST controller for unified audit events."""

    def __init__(
        self,
        audit_service_manager: AuditServiceManager,
        database_service_manager: object | None = None,
        auth_service_manager: object | None = None,
    ) -> None:
        _ = database_service_manager, auth_service_manager
        self.manager = audit_service_manager

    @staticmethod
    def _route_dependencies(security: DependsParam | None) -> list[DependsParam] | None:
        return [security] if security else None

    def prepare(self, app: APIRouter, security: DependsParam | None = None) -> None:
        route_dependencies = self._route_dependencies(security)

        @app.get(
            "/audit-events",
            response_model=AuditEventListResponse,
            tags=["audit"],
            dependencies=route_dependencies,
        )
        def list_audit_events(
            request: Request,
            actor: AuditReadActor,
            entity_id: str | None = Query(default=None),
            user_id: str | None = Query(default=None),
            metadata_type: list[str] | None = Query(default=None),
            event_type: str | None = Query(default=None),
            date_from: date | None = Query(default=None),
            date_to: date | None = Query(default=None),
            limit: int = Query(default=50, ge=1, le=200),
            offset: int = Query(default=0, ge=0),
        ) -> AuditEventListResponse:
            request_id = getattr(request.state, "request_id", "")
            with tracer.start_as_current_span("AuditRestController.list_audit_events"):
                try:
                    return self.manager.list_audit_events_for_actor(
                        actor,
                        entity_id=entity_id,
                        user_id=user_id,
                        metadata_type=metadata_type,
                        event_type=event_type,
                        date_from=date_from,
                        date_to=date_to,
                        limit=limit,
                        offset=offset,
                    )
                except Exception as exc:
                    raise_http_error(
                        exc,
                        {"request_id": request_id, "operation": "list_audit_events"},
                    )

        @app.get(
            "/audit-events/field-changes",
            response_model=AuditEventListResponse,
            tags=["audit"],
            dependencies=route_dependencies,
        )
        def list_field_changes(
            request: Request,
            actor: LogsReadActor,
            user_id: str | None = Query(default=None),
            date_from: date | None = Query(default=None),
            date_to: date | None = Query(default=None),
            limit: int = Query(default=50, ge=1, le=200),
            offset: int = Query(default=0, ge=0),
        ) -> AuditEventListResponse:
            """Org-wide record change history. Never scoped to one record, so it
            carries `logs:read` rather than the record-read gate `/audit-events`
            uses. Event scope is pinned server-side."""
            request_id = getattr(request.state, "request_id", "")
            with tracer.start_as_current_span("AuditRestController.list_field_changes"):
                try:
                    return self.manager.list_audit_events_for_actor(
                        actor,
                        metadata_type=AuditMetadataType.ENTITY.value,
                        event_type=list(LOGS_EVENT_TYPES),
                        actor_type="user",
                        user_id=user_id,
                        date_from=date_from,
                        date_to=date_to,
                        limit=limit,
                        offset=offset,
                    )
                except Exception as exc:
                    raise_http_error(
                        exc,
                        {"request_id": request_id, "operation": "list_field_changes"},
                    )

        @app.get(
            "/audit-events/constants",
            response_model=AuditConstantsResponse,
            tags=["audit"],
            dependencies=route_dependencies,
        )
        def get_audit_constants(
            request: Request,
            actor: AuditReadActor,
        ) -> AuditConstantsResponse:
            request_id = getattr(request.state, "request_id", "")
            with tracer.start_as_current_span("AuditRestController.get_audit_constants"):
                try:
                    return self.manager.get_constants()
                except Exception as exc:
                    raise_http_error(
                        exc,
                        {"request_id": request_id, "operation": "get_audit_constants"},
                    )
