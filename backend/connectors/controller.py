"""Connectors REST controller module."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Request, status

from common.auth import actor_str, require_permission
from common.logger import logger, tracer
from common.utils import raise_http_error
from exceptions import NotFoundError
from connectors.models.request import (
    ConnectorCreateRequest,
    ConnectorInlineTestRequest,
    ConnectorTestRequest,
    ConnectorUpdateRequest,
)
from connectors.models.response import (
    ConnectorListResponse,
    ConnectorReadResponse,
    ConnectorsStatusResponse,
    ConnectorTestResponse,
)

if TYPE_CHECKING:
    from fastapi.params import Depends as DependsParam

    from auth.manager import AuthServiceManager
    from connectors.manager import ConnectorsServiceManager
    from database.manager import DatabaseServiceManager

ConnectorReadActor = Annotated[
    dict[str, object], Depends(require_permission("connector", "read"))
]
ConnectorWriteActor = Annotated[
    dict[str, object], Depends(require_permission("connector", "write"))
]


class ConnectorsRestController:
    """Implements the connectors REST controller."""

    def __init__(
        self,
        connectors_service_manager: ConnectorsServiceManager,
        database_service_manager: DatabaseServiceManager | None = None,
        auth_service_manager: AuthServiceManager | None = None,
    ) -> None:
        self.manager = connectors_service_manager
        self.database_service_manager = database_service_manager
        self.auth_service_manager = auth_service_manager

    @staticmethod
    def _route_dependencies(security: DependsParam | None) -> list[DependsParam] | None:
        return [security] if security else None

    @staticmethod
    def _error_context(request_id: str, operation: str) -> dict[str, str]:
        return {
            "request_id": request_id,
            "controller": "ConnectorsRestController",
            "operation": operation,
        }

    @staticmethod
    def _org_id(actor: dict[str, object]) -> str:
        return actor_str(actor, "organization_id")

    def prepare(self, app: APIRouter, security: DependsParam | None = None) -> None:
        """Register all connector routes on the router."""
        route_dependencies = self._route_dependencies(security)

        @app.get(
            "/connectors/status",
            status_code=status.HTTP_200_OK,
            tags=["connectors"],
            response_model=ConnectorsStatusResponse,
            dependencies=route_dependencies,
        )
        def status_endpoint(request: Request):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ConnectorsController.status"):
                try:
                    return self.manager.get_status()
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "status"))

        @app.get(
            "/connectors",
            status_code=status.HTTP_200_OK,
            tags=["connectors"],
            response_model=ConnectorListResponse,
            dependencies=route_dependencies,
        )
        def list_connectors_endpoint(
            request: Request, actor: ConnectorReadActor, entity_type: str | None = None
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ConnectorsController.list"):
                try:
                    logger.info("connectors list requested", extra={"request_id": request_id})
                    return self.manager.list_connectors_for_actor(
                        actor, self._org_id(actor), entity_type
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "list_connectors"))

        @app.post(
            "/connectors",
            status_code=status.HTTP_201_CREATED,
            tags=["connectors"],
            response_model=ConnectorReadResponse,
            dependencies=route_dependencies,
        )
        def create_connector_endpoint(
            request: Request, payload: ConnectorCreateRequest, actor: ConnectorWriteActor
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ConnectorsController.create"):
                try:
                    logger.info("connector create requested", extra={"request_id": request_id})
                    return self.manager.create_connector_for_actor(
                        actor, self._org_id(actor), payload
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "create_connector"))

        @app.get(
            "/connectors/{connector_id}",
            status_code=status.HTTP_200_OK,
            tags=["connectors"],
            response_model=ConnectorReadResponse,
            dependencies=route_dependencies,
        )
        def get_connector_endpoint(
            request: Request, connector_id: str, actor: ConnectorReadActor
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ConnectorsController.get"):
                try:
                    return self.manager.get_connector_for_actor(
                        actor, self._org_id(actor), connector_id
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "get_connector"))

        @app.patch(
            "/connectors/{connector_id}",
            status_code=status.HTTP_200_OK,
            tags=["connectors"],
            response_model=ConnectorReadResponse,
            dependencies=route_dependencies,
        )
        def update_connector_endpoint(
            request: Request,
            connector_id: str,
            payload: ConnectorUpdateRequest,
            actor: ConnectorWriteActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ConnectorsController.update"):
                try:
                    logger.info("connector update requested", extra={"request_id": request_id})
                    return self.manager.update_connector_for_actor(
                        actor, self._org_id(actor), connector_id, payload
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "update_connector"))

        @app.delete(
            "/connectors/{connector_id}",
            status_code=status.HTTP_204_NO_CONTENT,
            tags=["connectors"],
            dependencies=route_dependencies,
        )
        def delete_connector_endpoint(
            request: Request, connector_id: str, actor: ConnectorWriteActor
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ConnectorsController.delete"):
                try:
                    logger.info("connector delete requested", extra={"request_id": request_id})
                    deleted = self.manager.delete_connector_for_actor(
                        actor, self._org_id(actor), connector_id
                    )
                    if not deleted:
                        raise NotFoundError("Connector not found")
                    return None
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "delete_connector"))

        @app.post(
            "/connectors/test-inline",
            status_code=status.HTTP_200_OK,
            tags=["connectors"],
            response_model=ConnectorTestResponse,
            dependencies=route_dependencies,
        )
        def test_connector_inline_endpoint(
            request: Request,
            payload: ConnectorInlineTestRequest,
            actor: ConnectorWriteActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ConnectorsController.test_inline"):
                try:
                    logger.info("connector inline test requested", extra={"request_id": request_id})
                    return self.manager.test_connector_inline_for_actor(
                        actor, self._org_id(actor), payload
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "test_connector_inline"))

        @app.post(
            "/connectors/{connector_id}/test",
            status_code=status.HTTP_200_OK,
            tags=["connectors"],
            response_model=ConnectorTestResponse,
            dependencies=route_dependencies,
        )
        def test_connector_endpoint(
            request: Request,
            connector_id: str,
            payload: ConnectorTestRequest,
            actor: ConnectorWriteActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("ConnectorsController.test"):
                try:
                    logger.info("connector test requested", extra={"request_id": request_id})
                    return self.manager.test_connector_for_actor(
                        actor, self._org_id(actor), connector_id, payload
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "test_connector"))
