"""LLM REST controller module."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from common.auth import require_permission
from common.logger import logger, tracer
from common.utils import raise_http_error
from llm.models.response import AgentAiStatusResponse, LlmAvailableModelsResponse

if TYPE_CHECKING:
    from fastapi.params import Depends as DependsParam

    from auth.manager import AuthServiceManager
    from database.manager import DatabaseServiceManager
    from llm.manager import LlmServiceManager

LlmReadActor = Annotated[dict[str, object], Depends(require_permission("agent", "read"))]


class LlmRestController:
    """Implements llm REST controller."""

    def __init__(
        self,
        llm_service_manager: LlmServiceManager,
        database_service_manager: DatabaseServiceManager | None = None,
        auth_service_manager: AuthServiceManager | None = None,
    ) -> None:
        _ = database_service_manager, auth_service_manager
        self.llm_service_manager = llm_service_manager
        self.manager = llm_service_manager

    @staticmethod
    def _route_dependencies(security: DependsParam | None) -> list[DependsParam] | None:
        return [security] if security else None

    @staticmethod
    def _error_context(request_id: str, operation: str) -> dict[str, str]:
        return {
            "request_id": request_id,
            "controller": "LlmRestController",
            "operation": operation,
        }

    def prepare(self, app: APIRouter, security: DependsParam | None = None) -> None:
        """Prepare the LLM REST controller.

        Args:
            app: Router to mount endpoints on.
        """
        route_dependencies = self._route_dependencies(security)

        @app.get(
            "/llm/status",
            status_code=status.HTTP_200_OK,
            response_model=AgentAiStatusResponse,
            tags=["llm"],
            dependencies=route_dependencies,
        )
        def status_endpoint(request: Request) -> AgentAiStatusResponse:
            """Return the module status payload.

            Args:
                request: FastAPI request.

            Returns:
                AgentAiStatusResponse.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("LlmController.status"):
                try:
                    logger.info("llm status requested", extra={"request_id": request_id})
                    return self.llm_service_manager.get_status()
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "status"))

        @app.get(
            "/llm/models",
            status_code=status.HTTP_200_OK,
            response_model=LlmAvailableModelsResponse,
            tags=["llm"],
            dependencies=route_dependencies,
        )
        def list_models_endpoint(
            request: Request,
            actor: LlmReadActor,
            organization_id: str | None = Query(default=None, min_length=1),
        ) -> LlmAvailableModelsResponse:
            """List available LLM models for an organization.

            Args:
                request: FastAPI request.
                organization_id: Optional target organization id; defaults to actor org.
                actor: Actor context.

            Returns:
                LlmAvailableModelsResponse.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("LlmController.listModels"):
                try:
                    logger.info(
                        "llm available models requested",
                        extra={"request_id": request_id, "organization_id": organization_id},
                    )
                    return self.llm_service_manager.list_available_models_for_actor(actor, organization_id)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "list_models"))
