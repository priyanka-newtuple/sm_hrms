"""REST controller for the shared tools module."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from common.auth import require_permission
from common.logger import logger, tracer
from exceptions import AuthorizationError, ConflictError, DBException, NotFoundError, PersistenceError, RecordNotFoundException, ServiceError, ValidationError

from tools.manager import ToolsServiceManager
from tools.models.interface import ToolDescriptorContract, ToolExecutionLogContract, ToolPresetContract
from tools.models.request import ToolExecutionLogListRequest, ToolExecutionRequest
from tools.models.response import (
    ToolCatalogResponse,
    ToolExecutionLogListResponse,
    ToolExecutionResponse,
    ToolPresetListResponse,
)

# Actor types
ReadActor = Annotated[dict[str, object], Depends(require_permission("tool", "read"))]
WriteActor = Annotated[dict[str, object], Depends(require_permission("tool", "write"))]
# Execution-history is an audit surface: restrict it via the DB-backed
# permission catalog, scoped to the caller's own organization.
ExecutionLogActor = Annotated[dict[str, object], Depends(require_permission("tool_execution", "read"))]


class ToolsRestController:
    """Expose shared tool APIs and delegate business flow to the tools manager."""

    def __init__(
        self,
        tools_service_manager: ToolsServiceManager,
        database_service_manager=None,
        auth_service_manager=None,
    ) -> None:  # noqa: ANN001
        """Store manager dependencies used by the controller.

        Args:
            tools_service_manager: Tools manager that owns business orchestration.
            database_service_manager: Optional database manager reference.
            auth_service_manager: Optional auth manager reference.

        Returns:
            `None`.
        """
        _ = database_service_manager, auth_service_manager
        self.manager = tools_service_manager

    @staticmethod
    def _route_dependencies(security: Depends | None) -> list[Depends] | None:
        """Normalize optional route-level security dependencies.

        Args:
            security: Optional route-level dependency to wrap.

        Returns:
            A dependency list when security is provided, otherwise `None`.
        """
        return [security] if security else None

    @staticmethod
    def _raise_http(exc: Exception) -> None:
        """Translate module exceptions into HTTP exceptions.

        Args:
            exc: Raised application exception to convert.

        Returns:
            `None`.
        """
        if isinstance(exc, HTTPException):
            raise exc
        if isinstance(exc, (RecordNotFoundException, NotFoundError)):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        if isinstance(exc, (ValidationError, ValueError)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        if isinstance(exc, (AuthorizationError, PermissionError)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        if isinstance(exc, ConflictError):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        if isinstance(exc, (DBException, PersistenceError, ServiceError)):
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from exc

    def prepare(self, app: APIRouter, security: Depends | None = None) -> None:
        """Register tools routes on the supplied router.

        Args:
            app: Router that will receive the tools endpoints.
            security: Optional route-level security dependency.

        Returns:
            `None`.
        """
        route_dependencies = self._route_dependencies(security)

        # region Catalog Routes
        @app.get("/tools/catalog", response_model=ToolCatalogResponse, tags=["tools"], dependencies=route_dependencies)
        def list_catalog_endpoint(
            request: Request,
            actor: ReadActor,
        ) -> ToolCatalogResponse:
            """Return the canonical shared tools catalog.

            Args:
                request: FastAPI request carrying request-scoped metadata.
                actor: Authenticated actor context resolved from the request.

            Returns:
                The current tool catalog response.
            """
            _ = actor
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ToolsController.catalog"):
                try:
                    logger.info("tools catalog requested", extra={"request_id": request_id})
                    return self.manager.get_catalog()
                except Exception as exc:  # noqa: BLE001
                    self._raise_http(exc)

        @app.get("/tools/catalog/{tool_name}", response_model=ToolDescriptorContract, tags=["tools"], dependencies=route_dependencies)
        def get_catalog_item_endpoint(
            request: Request,
            tool_name: str,
            actor: ReadActor,
        ) -> ToolDescriptorContract:
            """Return one tool descriptor from the shared catalog.

            Args:
                request: FastAPI request carrying request-scoped metadata.
                tool_name: Tool name to resolve.
                actor: Authenticated actor context resolved from the request.

            Returns:
                The requested tool descriptor.
            """
            _ = actor
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ToolsController.catalog_item"):
                try:
                    logger.info("tool descriptor requested", extra={"request_id": request_id, "tool_name": tool_name})
                    return self.manager.get_tool_descriptor(tool_name)
                except Exception as exc:  # noqa: BLE001
                    self._raise_http(exc)

        @app.get("/tools/presets", response_model=ToolPresetListResponse, tags=["tools"], dependencies=route_dependencies)
        def list_presets_endpoint(
            request: Request,
            actor: ReadActor,
        ) -> ToolPresetListResponse:
            """Return the shared tool presets.

            Args:
                request: FastAPI request carrying request-scoped metadata.
                actor: Authenticated actor context resolved from the request.

            Returns:
                The current preset list response.
            """
            _ = actor
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ToolsController.presets"):
                try:
                    logger.info("tools presets requested", extra={"request_id": request_id})
                    return self.manager.get_presets()
                except Exception as exc:  # noqa: BLE001
                    self._raise_http(exc)

        @app.get("/tools/presets/{preset_name}", response_model=ToolPresetContract, tags=["tools"], dependencies=route_dependencies)
        def get_preset_endpoint(
            request: Request,
            preset_name: str,
            actor: ReadActor,
        ) -> ToolPresetContract:
            """Return one named tool preset.

            Args:
                request: FastAPI request carrying request-scoped metadata.
                preset_name: Preset name to resolve.
                actor: Authenticated actor context resolved from the request.

            Returns:
                The requested tool preset.
            """
            _ = actor
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ToolsController.preset_item"):
                try:
                    logger.info("tool preset requested", extra={"request_id": request_id, "preset_name": preset_name})
                    return self.manager.get_preset(preset_name)
                except Exception as exc:  # noqa: BLE001
                    self._raise_http(exc)

        # endregion Catalog Routes

        # region Execution Routes
        @app.post("/tools/execute", response_model=ToolExecutionResponse, tags=["tools"], dependencies=route_dependencies)
        def execute_tool_endpoint(
            request: Request,
            payload: ToolExecutionRequest,
            actor: WriteActor,
        ) -> ToolExecutionResponse:
            """Execute one shared tool directly through the tools module.

            Args:
                request: FastAPI request carrying request-scoped metadata.
                payload: Typed tool-execution request payload.
                actor: Authenticated actor context resolved from the request.

            Returns:
                The normalized tool execution response.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ToolsController.execute_tool"):
                try:
                    logger.info("tool execution requested", extra={"request_id": request_id, "tool_name": payload.tool_name})
                    return ToolExecutionResponse(result=self.manager.execute_tool_for_actor(actor, payload))
                except Exception as exc:  # noqa: BLE001
                    self._raise_http(exc)

        @app.get("/tools/executions", response_model=ToolExecutionLogListResponse, tags=["tools"], dependencies=route_dependencies)
        def list_execution_logs_endpoint(
            request: Request,
            actor: ExecutionLogActor,
            limit: int = Query(default=20, ge=1, le=100),
            offset: int = Query(default=0, ge=0),
            tool_name: str | None = Query(default=None),
            source: str | None = Query(default=None),
            success: bool | None = Query(default=None),
            execution_backend: str | None = Query(default=None),
        ) -> ToolExecutionLogListResponse:
            """List persisted tool execution audit rows for the actor's organization.

            Args:
                request: FastAPI request carrying request-scoped metadata.
                actor: Authenticated admin actor context resolved from the request.
                limit: Maximum rows to return.
                offset: Row offset for pagination.
                tool_name: Optional tool-name filter.
                source: Optional execution-source filter.
                success: Optional success filter.
                execution_backend: Optional backend filter.

            Returns:
                Paginated execution-history rows.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            query = ToolExecutionLogListRequest(
                limit=limit,
                offset=offset,
                tool_name=tool_name,
                source=source,
                success=success,
                execution_backend=execution_backend,
            )
            with tracer.start_as_current_span("ToolsController.list_executions"):
                try:
                    logger.info("tool execution history requested", extra={"request_id": request_id})
                    return self.manager.list_executions_for_actor(actor, query)
                except Exception as exc:  # noqa: BLE001
                    self._raise_http(exc)

        @app.get("/tools/executions/{execution_id}", response_model=ToolExecutionLogContract, tags=["tools"], dependencies=route_dependencies)
        def get_execution_log_endpoint(
            request: Request,
            execution_id: str,
            actor: ExecutionLogActor,
        ) -> ToolExecutionLogContract:
            """Return one persisted tool execution audit row.

            Args:
                request: FastAPI request carrying request-scoped metadata.
                execution_id: Execution-log identifier to resolve.
                actor: Authenticated admin actor context resolved from the request.

            Returns:
                The requested execution-history row.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ToolsController.get_execution"):
                try:
                    logger.info("tool execution detail requested", extra={"request_id": request_id, "execution_id": execution_id})
                    return self.manager.get_execution_for_actor(actor, execution_id)
                except Exception as exc:  # noqa: BLE001
                    self._raise_http(exc)

        # endregion Execution Routes

        # region Document Configuration Alias Routes
        @app.get("/config/document-types/tools", response_model=ToolCatalogResponse, tags=["tools"], dependencies=route_dependencies)
        def document_config_catalog_endpoint(
            request: Request,
            actor: ReadActor,
        ) -> ToolCatalogResponse:
            """Return the document-configuration alias for the shared tool catalog.

            Args:
                request: FastAPI request carrying request-scoped metadata.
                actor: Authenticated actor context resolved from the request.

            Returns:
                The canonical tool catalog response.
            """
            _ = actor
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ToolsController.document_config_catalog"):
                try:
                    logger.info("document config tool catalog requested", extra={"request_id": request_id})
                    return self.manager.get_catalog()
                except Exception as exc:  # noqa: BLE001
                    self._raise_http(exc)

        @app.get("/config/document-types/tools/presets", response_model=ToolPresetListResponse, tags=["tools"], dependencies=route_dependencies)
        def document_config_presets_endpoint(
            request: Request,
            actor: ReadActor,
        ) -> ToolPresetListResponse:
            """Return the document-configuration alias for the shared tool presets.

            Args:
                request: FastAPI request carrying request-scoped metadata.
                actor: Authenticated actor context resolved from the request.

            Returns:
                The canonical tool preset list response.
            """
            _ = actor
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ToolsController.document_config_presets"):
                try:
                    logger.info("document config tool presets requested", extra={"request_id": request_id})
                    return self.manager.get_presets()
                except Exception as exc:  # noqa: BLE001
                    self._raise_http(exc)

        # endregion Document Configuration Alias Routes
