"""Custom forms REST controller module."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Request, status

from common.auth import actor_str, require_permission
from common.logger import logger, tracer
from common.utils import raise_http_error
from custom_forms.models.request import ConnectorFormPreviewRequest
from custom_forms.models.response import ConnectorFormPreviewResponse

if TYPE_CHECKING:
    from fastapi.params import Depends as DependsParam

    from auth.manager import AuthServiceManager
    from custom_forms.manager import CustomFormsServiceManager
    from database.manager import DatabaseServiceManager

CustomFormPreviewActor = Annotated[
    dict[str, object], Depends(require_permission("entity_record", "write"))
]


class CustomFormsRestController:
    """Implements the custom forms REST controller."""

    def __init__(
        self,
        custom_forms_service_manager: CustomFormsServiceManager,
        database_service_manager: DatabaseServiceManager | None = None,
        auth_service_manager: AuthServiceManager | None = None,
    ) -> None:
        self.manager = custom_forms_service_manager
        self.database_service_manager = database_service_manager
        self.auth_service_manager = auth_service_manager

    @staticmethod
    def _route_dependencies(security: DependsParam | None) -> list[DependsParam] | None:
        return [security] if security else None

    @staticmethod
    def _error_context(request_id: str, operation: str) -> dict[str, str]:
        return {
            "request_id": request_id,
            "controller": "CustomFormsRestController",
            "operation": operation,
        }

    @staticmethod
    def _org_id(actor: dict[str, object]) -> str:
        return actor_str(actor, "organization_id")

    def prepare(self, app: APIRouter, security: DependsParam | None = None) -> None:
        """Register all custom forms routes on the router."""
        route_dependencies = self._route_dependencies(security)

        @app.post(
            "/custom-forms/methods/{method_version_id}/preview",
            status_code=status.HTTP_200_OK,
            tags=["custom-forms"],
            response_model=ConnectorFormPreviewResponse,
            dependencies=route_dependencies,
        )
        def preview_connector_form_endpoint(
            request: Request,
            method_version_id: str,
            payload: ConnectorFormPreviewRequest,
            actor: CustomFormPreviewActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("CustomFormsController.preview"):
                try:
                    logger.info(
                        "custom form preview requested", extra={"request_id": request_id}
                    )
                    return self.manager.resolve_connector_form_for_actor(
                        actor, self._org_id(actor), method_version_id, payload.entity_values
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "preview_connector_form"))
