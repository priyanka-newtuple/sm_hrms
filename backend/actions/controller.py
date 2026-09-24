"""Actions REST controller."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, Request, status

from common.auth import require_permission
from common.deps import get_db
from common.logger import logger, tracer
from common.utils import raise_http_error

if TYPE_CHECKING:
    from fastapi.params import Depends as DependsParam

    from actions.manager import ActionsServiceManager
    from auth.manager import AuthServiceManager
    from database.manager import DatabaseServiceManager

ActionReadActor = Annotated[dict[str, object], Depends(require_permission("entity_record", "read"))]


class ActionsRestController:
    """Expose action definition and action run APIs."""

    def __init__(
        self,
        actions_service_manager: ActionsServiceManager,
        database_service_manager: DatabaseServiceManager | None = None,
        auth_service_manager: AuthServiceManager | None = None,
    ) -> None:
        """Store the service manager; unused dependencies accepted for interface compatibility."""
        _ = database_service_manager, auth_service_manager
        self.manager = actions_service_manager

    @staticmethod
    def _route_dependencies(security: DependsParam | None) -> list[DependsParam] | None:
        """Wrap the security dependency in a list, or return None if no security is provided."""
        return [security] if security else None

    @staticmethod
    def _error_context(request_id: str, operation: str) -> dict[str, str]:
        """Build a structured error context dict for consistent error reporting."""
        return {
            "request_id": request_id,
            "controller": "ActionsRestController",
            "operation": operation,
        }

    def prepare(self, app: APIRouter, security: DependsParam | None = None) -> None:
        """Register all action routes on the given router."""
        route_dependencies = self._route_dependencies(security)

        @app.get(
            "/action-definitions",
            status_code=status.HTTP_200_OK,
            tags=["actions"],
            dependencies=route_dependencies,
        )
        def list_action_definitions(
            request: Request,
            actor: ActionReadActor,
            db: Any = Depends(get_db),
        ):
            """Return all registered action definitions available for use in workflows."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ActionsController.list_action_definitions"):
                try:
                    logger.info("actions.list_action_definitions", extra={"request_id": request_id})
                    return {
                        "items": self.manager.list_action_definitions(
                            db, org_id=str(actor["organization_id"])
                        )
                    }
                except Exception as exc:
                    raise_http_error(
                        exc, self._error_context(request_id, "list_action_definitions")
                    )

        @app.get(
            "/action-definitions/{kind}",
            status_code=status.HTTP_200_OK,
            tags=["actions"],
            dependencies=route_dependencies,
        )
        def get_action_definition(
            request: Request,
            kind: str,
            actor: ActionReadActor,
            db: Any = Depends(get_db),
        ):
            """Return a single action definition by its kind identifier."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ActionsController.get_action_definition"):
                try:
                    logger.info(
                        "actions.get_action_definition",
                        extra={"request_id": request_id, "kind": kind},
                    )
                    return self.manager.get_action_definition_by_kind(db, kind)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "get_action_definition"))
