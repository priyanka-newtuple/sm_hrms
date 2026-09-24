"""REST controller for platform-managed MCP capabilities."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Request

from common.auth import require_permission
from common.logger import logger, tracer
from common.utils import raise_http_error
from mcp.models.request import McpCapabilityConfigurationUpdate, McpServerConfigurationUpdate
from mcp.models.response import (
    McpCapabilityResponse,
    McpServerPackageResponse,
    McpToolingOverviewResponse,
)

if TYPE_CHECKING:
    from fastapi.params import Depends as DependsParam

    from auth.manager import AuthServiceManager
    from database.manager import DatabaseServiceManager
    from mcp.manager import McpServiceManager

McpReadActor = Annotated[dict[str, object], Depends(require_permission("agent", "read"))]
McpWriteActor = Annotated[dict[str, object], Depends(require_permission("agent", "write"))]


class McpRestController:
    """Expose the minimal MCP package configuration API."""

    def __init__(
        self,
        mcp_service_manager: McpServiceManager,
        database_service_manager: DatabaseServiceManager | None = None,
        auth_service_manager: AuthServiceManager | None = None,
    ) -> None:
        _ = database_service_manager, auth_service_manager
        self.manager = mcp_service_manager

    @staticmethod
    def _route_dependencies(security: DependsParam | None) -> list[DependsParam] | None:
        return [security] if security else None

    def prepare(self, app: APIRouter, security: DependsParam | None = None) -> None:
        route_dependencies = self._route_dependencies(security)

        @app.get(
            "/mcp/tooling",
            response_model=McpToolingOverviewResponse,
            tags=["mcp"],
            dependencies=route_dependencies,
        )
        def get_tooling_endpoint(
            request: Request,
            actor: McpReadActor,
        ) -> McpToolingOverviewResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("McpController.get_tooling"):
                try:
                    logger.info("mcp tooling requested", extra={"request_id": request_id})
                    return self.manager.get_tooling_overview_for_actor(actor)
                except Exception as exc:  # noqa: BLE001
                    raise_http_error(
                        exc,
                        {
                            "request_id": request_id,
                            "controller": "McpRestController",
                            "operation": "get_tooling",
                        },
                    )

        @app.patch(
            "/mcp/server-packages/{package_id}/configuration",
            response_model=McpServerPackageResponse,
            tags=["mcp"],
            dependencies=route_dependencies,
        )
        def update_server_configuration_endpoint(
            request: Request,
            package_id: str,
            payload: McpServerConfigurationUpdate,
            actor: McpWriteActor,
        ) -> McpServerPackageResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("McpController.update_server_configuration"):
                try:
                    return self.manager.update_server_configuration_for_actor(
                        actor, package_id, payload
                    )
                except Exception as exc:  # noqa: BLE001
                    raise_http_error(
                        exc,
                        {
                            "request_id": request_id,
                            "controller": "McpRestController",
                            "operation": "update_server_configuration",
                        },
                    )

        @app.patch(
            "/mcp/capabilities/{capability_id}/configuration",
            response_model=McpCapabilityResponse,
            tags=["mcp"],
            dependencies=route_dependencies,
        )
        def update_capability_configuration_endpoint(
            request: Request,
            capability_id: str,
            payload: McpCapabilityConfigurationUpdate,
            actor: McpWriteActor,
        ) -> McpCapabilityResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("McpController.update_capability_configuration"):
                try:
                    return self.manager.update_capability_configuration_for_actor(
                        actor, capability_id, payload
                    )
                except Exception as exc:  # noqa: BLE001
                    raise_http_error(
                        exc,
                        {
                            "request_id": request_id,
                            "controller": "McpRestController",
                            "operation": "update_capability_configuration",
                        },
                    )
