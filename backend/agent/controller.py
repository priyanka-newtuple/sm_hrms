"""REST controller for the phase-1 agent runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from agent.models.request import (
    AgentDefinitionCreate,
    AgentDefinitionUpdate,
    AgentResumeRequest,
    AgentRunRequest,
    AgentSessionUpdateRequest,
)
from agent.models.response import (
    AgentDefinitionListResponse,
    AgentDefinitionResponse,
    AgentRunListResponse,
    AgentRunResponse,
    AgentSessionResponse,
    AgentTraceRunDetailResponse,
    AgentTraceRunListResponse,
    AgentTraceSessionListResponse,
    SessionWithMessagesResponse,
)
from common.auth import require_permission
from common.logger import logger, tracer
from common.utils import raise_http_error

if TYPE_CHECKING:
    from fastapi.params import Depends as DependsParam

    from agent.manager import AgentServiceManager
    from auth.manager import AuthServiceManager
    from database.manager import DatabaseServiceManager

AgentReadActor = Annotated[dict[str, object], Depends(require_permission("agent", "read"))]
AgentWriteActor = Annotated[dict[str, object], Depends(require_permission("agent", "write"))]
AgentTraceReadActor = Annotated[
    dict[str, object], Depends(require_permission("agent_trace", "read"))
]


class AgentRestController:
    """Expose the minimal phase-1 agent API and delegate to the manager."""

    def __init__(
        self,
        agent_service_manager: AgentServiceManager,
        database_service_manager: DatabaseServiceManager | None = None,
        auth_service_manager: AuthServiceManager | None = None,
    ) -> None:
        _ = database_service_manager, auth_service_manager
        self.manager = agent_service_manager

    @staticmethod
    def _route_dependencies(security: DependsParam | None) -> list[DependsParam] | None:
        return [security] if security else None

    def prepare(self, app: APIRouter, security: DependsParam | None = None) -> None:
        route_dependencies = self._route_dependencies(security)

        @app.get(
            "/agent/definitions",
            response_model=list[AgentDefinitionListResponse],
            tags=["agent"],
            dependencies=route_dependencies,
        )
        def list_definitions_endpoint(
            actor: AgentReadActor,
            request: Request,
            active_only: bool = Query(default=True),
            include_agent_mode: bool = Query(default=False),
        ) -> list[AgentDefinitionListResponse]:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("AgentController.list_definitions"):
                try:
                    logger.info("agent definitions requested", extra={"request_id": request_id})
                    return self.manager.list_definitions_for_actor(
                        actor, active_only=active_only, include_agent_mode=include_agent_mode
                    )
                except Exception as exc:
                    raise_http_error(
                        exc,
                        {
                            "request_id": request_id,
                            "controller": "AgentRestController",
                            "operation": "list_definitions",
                        },
                    )

        @app.get(
            "/agent/definitions/agent-mode",
            response_model=AgentDefinitionResponse,
            tags=["agent"],
            dependencies=route_dependencies,
        )
        def get_agent_mode_definition_endpoint(
            request: Request,
            actor: AgentReadActor,
        ) -> AgentDefinitionResponse:
            # Registered before /{definition_id} so "agent-mode" isn't captured as an id.
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("AgentController.get_agent_mode_definition"):
                try:
                    logger.info("agent mode definition requested", extra={"request_id": request_id})
                    return self.manager.get_agent_mode_definition_for_actor(actor)
                except Exception as exc:
                    raise_http_error(
                        exc,
                        {
                            "request_id": request_id,
                            "controller": "AgentRestController",
                            "operation": "get_agent_mode_definition",
                        },
                    )

        @app.get(
            "/agent/definitions/{definition_id}",
            response_model=AgentDefinitionResponse,
            tags=["agent"],
            dependencies=route_dependencies,
        )
        def get_definition_endpoint(
            request: Request,
            definition_id: str,
            actor: AgentReadActor,
        ) -> AgentDefinitionResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("AgentController.get_definition"):
                try:
                    logger.info(
                        "agent definition requested",
                        extra={"request_id": request_id, "definition_id": definition_id},
                    )
                    return self.manager.get_definition_for_actor(actor, definition_id)
                except Exception as exc:
                    raise_http_error(
                        exc,
                        {
                            "request_id": request_id,
                            "controller": "AgentRestController",
                            "operation": "get_definition",
                        },
                    )

        @app.post(
            "/agent/definitions",
            response_model=AgentDefinitionResponse,
            tags=["agent"],
            dependencies=route_dependencies,
            status_code=status.HTTP_201_CREATED,
        )
        def create_definition_endpoint(
            request: Request,
            payload: AgentDefinitionCreate,
            actor: AgentWriteActor,
        ) -> AgentDefinitionResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("AgentController.create_definition"):
                try:
                    logger.info(
                        "agent definition create requested", extra={"request_id": request_id}
                    )
                    return self.manager.create_definition_for_actor(actor, payload)
                except Exception as exc:
                    raise_http_error(
                        exc,
                        {
                            "request_id": request_id,
                            "controller": "AgentRestController",
                            "operation": "create_definition",
                        },
                    )

        @app.patch(
            "/agent/definitions/{definition_id}",
            response_model=AgentDefinitionResponse,
            tags=["agent"],
            dependencies=route_dependencies,
        )
        def update_definition_endpoint(
            request: Request,
            definition_id: str,
            payload: AgentDefinitionUpdate,
            actor: AgentWriteActor,
        ) -> AgentDefinitionResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("AgentController.update_definition"):
                try:
                    logger.info(
                        "agent definition update requested",
                        extra={"request_id": request_id, "definition_id": definition_id},
                    )
                    return self.manager.update_definition_for_actor(actor, definition_id, payload)
                except Exception as exc:
                    raise_http_error(
                        exc,
                        {
                            "request_id": request_id,
                            "controller": "AgentRestController",
                            "operation": "update_definition",
                        },
                    )

        @app.post(
            "/agent/runs",
            response_model=AgentRunResponse,
            tags=["agent"],
            dependencies=route_dependencies,
            status_code=status.HTTP_201_CREATED,
        )
        def create_run_endpoint(
            request: Request,
            payload: AgentRunRequest,
            actor: AgentWriteActor,
        ) -> AgentRunResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("AgentController.create_run"):
                try:
                    logger.info("agent run requested", extra={"request_id": request_id})
                    return self.manager.run_agent_for_actor(actor, payload)
                except Exception as exc:
                    raise_http_error(
                        exc,
                        {
                            "request_id": request_id,
                            "controller": "AgentRestController",
                            "operation": "create_run",
                        },
                    )

        @app.post(
            "/agent/async_runs",
            response_model=AgentRunResponse,
            tags=["agent"],
            dependencies=route_dependencies,
            status_code=status.HTTP_202_ACCEPTED,
        )
        def create_async_run_endpoint(
            request: Request,
            payload: AgentRunRequest,
            actor: AgentWriteActor,
        ) -> AgentRunResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("AgentController.create_async_run"):
                try:
                    logger.info("async agent run requested", extra={"request_id": request_id})
                    return self.manager.async_run_agent_for_actor(actor, payload)
                except Exception as exc:
                    raise_http_error(
                        exc,
                        {
                            "request_id": request_id,
                            "controller": "AgentRestController",
                            "operation": "create_async_run",
                        },
                    )

        @app.get(
            "/agent/runs",
            response_model=AgentRunListResponse,
            tags=["agent"],
            dependencies=route_dependencies,
        )
        def list_runs_endpoint(
            request: Request,
            actor: AgentReadActor,
            limit: int = Query(default=50, ge=1, le=200),
            offset: int = Query(default=0, ge=0),
            status_filter: str | None = Query(default=None, alias="status"),
            definition_id: str | None = Query(default=None),
        ) -> AgentRunListResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("AgentController.list_runs"):
                try:
                    logger.info("agent runs requested", extra={"request_id": request_id})
                    return self.manager.list_agent_runs_for_actor(
                        actor,
                        limit=limit,
                        offset=offset,
                        status=status_filter,
                        definition_id=definition_id,
                    )
                except Exception as exc:
                    raise_http_error(
                        exc,
                        {
                            "request_id": request_id,
                            "controller": "AgentRestController",
                            "operation": "list_runs",
                        },
                    )

        @app.get(
            "/agent/runs/{run_id}",
            response_model=AgentRunResponse,
            tags=["agent"],
            dependencies=route_dependencies,
        )
        def get_run_endpoint(
            request: Request,
            run_id: str,
            actor: AgentReadActor,
        ) -> AgentRunResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("AgentController.get_run"):
                try:
                    logger.info(
                        "agent run detail requested",
                        extra={"request_id": request_id, "run_id": run_id},
                    )
                    return self.manager.get_agent_run_for_actor(actor, run_id)
                except Exception as exc:
                    raise_http_error(
                        exc,
                        {
                            "request_id": request_id,
                            "controller": "AgentRestController",
                            "operation": "get_run",
                        },
                    )

        @app.get(
            "/agent-traces/runs",
            response_model=AgentTraceRunListResponse,
            tags=["agent-traces"],
            dependencies=route_dependencies,
        )
        def list_trace_runs_endpoint(
            request: Request,
            actor: AgentTraceReadActor,
            limit: int = Query(default=50, ge=1, le=200),
            offset: int = Query(default=0, ge=0),
            status_filter: str | None = Query(default=None, alias="status"),
            agent_name: str | None = Query(default=None),
            run_type: str | None = Query(default=None),
            session_id: str | None = Query(default=None),
        ) -> AgentTraceRunListResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("AgentController.list_trace_runs"):
                try:
                    logger.info("agent trace runs requested", extra={"request_id": request_id})
                    return self.manager.list_trace_runs_for_actor(
                        actor,
                        limit=limit,
                        offset=offset,
                        status=status_filter,
                        agent_name=agent_name,
                        run_type=run_type,
                        session_id=session_id,
                    )
                except Exception as exc:
                    raise_http_error(
                        exc,
                        {
                            "request_id": request_id,
                            "controller": "AgentRestController",
                            "operation": "list_trace_runs",
                        },
                    )

        @app.get(
            "/agent-traces/sessions",
            response_model=AgentTraceSessionListResponse,
            tags=["agent-traces"],
            dependencies=route_dependencies,
        )
        def list_trace_sessions_endpoint(
            request: Request,
            actor: AgentTraceReadActor,
            limit: int = Query(default=50, ge=1, le=200),
            offset: int = Query(default=0, ge=0),
            status_filter: str | None = Query(default=None, alias="status"),
            agent_name: str | None = Query(default=None),
            run_type: str | None = Query(default=None),
        ) -> AgentTraceSessionListResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("AgentController.list_trace_sessions"):
                try:
                    logger.info("agent trace sessions requested", extra={"request_id": request_id})
                    return self.manager.list_trace_sessions_for_actor(
                        actor,
                        limit=limit,
                        offset=offset,
                        status=status_filter,
                        agent_name=agent_name,
                        run_type=run_type,
                    )
                except Exception as exc:
                    raise_http_error(
                        exc,
                        {
                            "request_id": request_id,
                            "controller": "AgentRestController",
                            "operation": "list_trace_sessions",
                        },
                    )

        @app.get(
            "/agent-traces/runs/{run_id}",
            response_model=AgentTraceRunDetailResponse,
            tags=["agent-traces"],
            dependencies=route_dependencies,
        )
        def get_trace_run_endpoint(
            request: Request,
            run_id: str,
            actor: AgentTraceReadActor,
        ) -> AgentTraceRunDetailResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("AgentController.get_trace_run"):
                try:
                    logger.info(
                        "agent trace run detail requested",
                        extra={"request_id": request_id, "run_id": run_id},
                    )
                    return self.manager.get_trace_run_for_actor(actor, run_id)
                except Exception as exc:
                    raise_http_error(
                        exc,
                        {
                            "request_id": request_id,
                            "controller": "AgentRestController",
                            "operation": "get_trace_run",
                        },
                    )

        @app.get(
            "/agent/sessions",
            response_model=list[AgentSessionResponse],
            tags=["agent"],
            dependencies=route_dependencies,
        )
        def list_sessions_endpoint(
            request: Request,
            actor: AgentReadActor,
            limit: int = Query(default=20, ge=1, le=100),
            offset: int = Query(default=0, ge=0),
        ) -> list[AgentSessionResponse]:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("AgentController.list_sessions"):
                try:
                    logger.info("agent sessions requested", extra={"request_id": request_id})
                    return self.manager.list_sessions_for_actor(
                        actor,
                        limit=limit,
                        offset=offset,
                    )
                except Exception as exc:
                    raise_http_error(
                        exc,
                        {
                            "request_id": request_id,
                            "controller": "AgentRestController",
                            "operation": "list_sessions",
                        },
                    )

        @app.get(
            "/agent/sessions/{session_id}",
            response_model=SessionWithMessagesResponse,
            tags=["agent"],
            dependencies=route_dependencies,
        )
        def get_session_endpoint(
            request: Request,
            session_id: str,
            actor: AgentReadActor,
        ) -> SessionWithMessagesResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("AgentController.get_session"):
                try:
                    logger.info(
                        "agent session detail requested",
                        extra={"request_id": request_id, "session_id": session_id},
                    )
                    return self.manager.get_session_for_actor(actor, session_id)
                except Exception as exc:
                    raise_http_error(
                        exc,
                        {
                            "request_id": request_id,
                            "controller": "AgentRestController",
                            "operation": "get_session",
                        },
                    )

        @app.delete(
            "/agent/sessions/{session_id}",
            tags=["agent"],
            dependencies=route_dependencies,
        )
        def delete_session_endpoint(
            request: Request,
            session_id: str,
            actor: AgentWriteActor,
        ) -> dict[str, object]:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("AgentController.delete_session"):
                try:
                    logger.info(
                        "agent session delete requested",
                        extra={"request_id": request_id, "session_id": session_id},
                    )
                    deleted = self.manager.delete_session_for_actor(actor, session_id)
                    return {"success": deleted, "deleted_id": session_id if deleted else None}
                except Exception as exc:
                    raise_http_error(
                        exc,
                        {
                            "request_id": request_id,
                            "controller": "AgentRestController",
                            "operation": "delete_session",
                        },
                    )

        @app.patch(
            "/agent/sessions/{session_id}",
            response_model=AgentSessionResponse,
            tags=["agent"],
            dependencies=route_dependencies,
        )
        def rename_session_endpoint(
            request: Request,
            session_id: str,
            payload: AgentSessionUpdateRequest,
            actor: AgentWriteActor,
        ) -> AgentSessionResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("AgentController.rename_session"):
                try:
                    logger.info(
                        "agent session rename requested",
                        extra={"request_id": request_id, "session_id": session_id},
                    )
                    return self.manager.rename_session_for_actor(actor, session_id, payload.title)
                except Exception as exc:
                    raise_http_error(
                        exc,
                        {
                            "request_id": request_id,
                            "controller": "AgentRestController",
                            "operation": "rename_session",
                        },
                    )

        @app.post(
            "/agent/runs/{run_id}/resume",
            response_model=AgentRunResponse,
            tags=["agent"],
            dependencies=route_dependencies,
        )
        def resume_run_endpoint(
            request: Request,
            run_id: str,
            payload: AgentResumeRequest,
            actor: AgentWriteActor,
        ) -> AgentRunResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("AgentController.resume_run"):
                try:
                    logger.info(
                        "agent run resume requested",
                        extra={"request_id": request_id, "run_id": run_id},
                    )
                    return self.manager.resume_agent_run_for_actor(actor, run_id, payload)
                except Exception as exc:
                    raise_http_error(
                        exc,
                        {
                            "request_id": request_id,
                            "controller": "AgentRestController",
                            "operation": "resume_run",
                        },
                    )

        @app.post(
            "/agent/runs/{run_id}/cancel",
            response_model=AgentRunResponse,
            tags=["agent"],
            dependencies=route_dependencies,
        )
        def cancel_run_endpoint(
            request: Request,
            run_id: str,
            actor: AgentWriteActor,
        ) -> AgentRunResponse:
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("AgentController.cancel_run"):
                try:
                    logger.info(
                        "agent run cancel requested",
                        extra={"request_id": request_id, "run_id": run_id},
                    )
                    return self.manager.cancel_agent_run_for_actor(actor, run_id)
                except Exception as exc:
                    raise_http_error(
                        exc,
                        {
                            "request_id": request_id,
                            "controller": "AgentRestController",
                            "operation": "cancel_run",
                        },
                    )
