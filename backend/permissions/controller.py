"""Permissions REST controller — global permission catalog endpoint."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, Request

from common.auth import require_permission
from common.deps import get_db
from common.logger import logger, tracer
from common.utils import raise_http_error

from permissions.models.response import PermissionRead

if TYPE_CHECKING:
    from auth.manager import AuthServiceManager
    from database.manager import DatabaseServiceManager
    from permissions.manager import PermissionsServiceManager


PermissionReadActor = Annotated[dict[str, object], Depends(require_permission("role", "read"))]


class PermissionsRestController:
    """Permissions REST controller — exposes the system permission catalog."""

    def __init__(
        self,
        permissions_service_manager: PermissionsServiceManager,
        database_service_manager: DatabaseServiceManager | None = None,
        auth_service_manager: AuthServiceManager | None = None,
    ) -> None:
        _ = database_service_manager, auth_service_manager
        self.manager = permissions_service_manager

    @staticmethod
    def _error_context(request_id: str, operation: str) -> dict[str, str]:
        return {
            "request_id": request_id,
            "controller": "PermissionsRestController",
            "operation": operation,
        }

    def prepare(self, app: APIRouter) -> None:
        """Register all permission routes on the given router."""

        @app.get(
            "/permissions",
            response_model=list[PermissionRead],
            tags=["permissions"],
        )
        def list_permissions(
            request: Request,
            actor: PermissionReadActor,
            db: Any = Depends(get_db),
        ) -> list[PermissionRead]:
            """List all backend permissions available for role configuration."""
            _ = actor
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("PermissionsController.list"):
                try:
                    logger.info("permissions.list", extra={"request_id": request_id})
                    return self.manager.list_permissions(db)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "list"))
