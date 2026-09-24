"""Phase-1 orchestration for the agent runtime."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from agent.models.interface import AgentTemplateContract, RequestContext
from agent.models.response import (
    AgentDefinitionListResponse,
    AgentDefinitionResponse,
    AgentMessageResponse,
    AgentRunListResponse,
    AgentRunResponse,
    AgentSessionResponse,
    AgentTraceEventResponse,
    AgentTraceRunDetailResponse,
    AgentTraceRunListItem,
    AgentTraceRunListResponse,
    AgentTraceSessionListItem,
    AgentTraceSessionListResponse,
    SessionWithMessagesResponse,
)
from agent.services import (
    AgentContextService,
    AgentDefinitionService,
    AgentRuntimeService,
    OpenAIAgentsSdkRuntimeAdapter,
)
from common.auth import actor_str
from common.logger import logger
from exceptions import NotFoundError, ServiceError, ValidationError

if TYPE_CHECKING:
    from agent.models.request import (
        AgentDefinitionCreate,
        AgentDefinitionUpdate,
        AgentResumeRequest,
        AgentRunRequest,
    )

ActorContext = dict[str, object]


class AgentServiceManager:
    """Coordinate the phase-1 agent API through focused internal services."""

    def __init__(
        self,
        agent_db_model_service,
        database_service_manager=None,
        config=None,
        tools_service_manager=None,
        mcp_registry_service=None,
        llm_service_manager=None,
        auth_service_manager=None,
        system_agent_templates: list[AgentTemplateContract] | None = None,
        async_run_enqueue_fn=None,
        document_source_fn=None,
    ) -> None:
        _ = database_service_manager, config
        _ = auth_service_manager
        if agent_db_model_service is None:
            raise ServiceError("agent persistence dependency is not configured")

        self.db_model_service = agent_db_model_service
        self.llm_service_manager = llm_service_manager
        self.capability_resolver = None
        if mcp_registry_service is not None and tools_service_manager is not None:
            from agent.services import AgentCapabilityResolver

            self.capability_resolver = AgentCapabilityResolver(
                mcp_registry_service,
                tools_service_manager,
            )
        self.definition_service = AgentDefinitionService(
            self.db_model_service,
            builtin_templates=system_agent_templates,
            capability_resolver=self.capability_resolver,
            llm_service_manager=self.llm_service_manager,
        )
        self.context_service = AgentContextService(self.db_model_service)
        self.runtime_service = AgentRuntimeService(
            self.db_model_service,
            self.definition_service,
            self.context_service,
            OpenAIAgentsSdkRuntimeAdapter(llm_service_manager=self.llm_service_manager),
            capability_resolver=self.capability_resolver,
            # Vision guard: decide whether the run's model can accept image input.
            llm_service_manager=self.llm_service_manager,
            # Reads a stored file's bytes + content type by document_id (filehandler's
            # read_document_source); the runtime builds the base64 vision input from it.
            document_source_fn=document_source_fn,
        )
        # Enqueue callback for async agent runs (BackgroundJobsServiceManager.
        # enqueue_agent_run). Injected at construction from main.py since
        # background_jobs is built before the agent manager; None disables async
        # enqueue (the worker's startup reconcile still drains queued runs).
        self.async_run_enqueue_fn = async_run_enqueue_fn

    def list_definitions_for_actor(
        self, actor: ActorContext, active_only: bool = True, include_agent_mode: bool = False
    ) -> list[AgentDefinitionListResponse]:
        context = self._request_context(actor)
        definitions = self.definition_service.list_definitions(
            context, active_only=active_only, include_agent_mode=include_agent_mode
        )
        return [
            AgentDefinitionListResponse(
                definition_id=definition.definition_id,
                name=definition.name,
                display_name=definition.display_name,
                description=definition.description,
                is_active=definition.is_active,
                is_system=definition.is_system,
                tool_count=len(definition.allowed_tools or []),
                approval_count=len((definition.constraints or {}).get("require_approval", [])),
                suggestion_count=len(definition.suggestions or []),
            )
            for definition in definitions
        ]

    def get_definition_for_actor(
        self, actor: ActorContext, definition_id: str
    ) -> AgentDefinitionResponse:
        context = self._request_context(actor)
        definition = self.definition_service.get_definition(context, definition_id)
        return AgentDefinitionResponse.model_validate(definition)

    def get_agent_mode_definition_for_actor(self, actor: ActorContext) -> AgentDefinitionResponse:
        context = self._request_context(actor)
        definition = self.definition_service.get_agent_mode_definition(context)
        return AgentDefinitionResponse.model_validate(definition)

    def create_definition_for_actor(
        self, actor: ActorContext, request: AgentDefinitionCreate
    ) -> AgentDefinitionResponse:
        context = self._request_context(actor)
        definition = self.definition_service.create_definition(context, request)
        return AgentDefinitionResponse.model_validate(definition)

    def update_definition_for_actor(
        self,
        actor: ActorContext,
        definition_id: str,
        request: AgentDefinitionUpdate,
    ) -> AgentDefinitionResponse:
        context = self._request_context(actor)
        definition = self.definition_service.update_definition(context, definition_id, request)
        return AgentDefinitionResponse.model_validate(definition)

    def run_agent_for_actor(
        self, actor: ActorContext, request: AgentRunRequest
    ) -> AgentRunResponse:
        context = self._request_context(actor)
        run = self.runtime_service.run(context, request)
        return AgentRunResponse.model_validate(run)

    def async_run_agent_for_actor(
        self, actor: ActorContext, request: AgentRunRequest
    ) -> AgentRunResponse:
        """Create a ``queued`` run and enqueue it for background execution.

        Returns immediately with the queued run; the client polls
        ``GET /agent/runs/{run_id}`` for completion. If the enqueue callback is
        not wired the run is still persisted as ``queued`` and will be drained by
        the worker's startup reconciliation.
        """
        context = self._request_context(actor)
        run = self.runtime_service.async_run(context, request)
        if self.async_run_enqueue_fn is not None:
            self.async_run_enqueue_fn(run.run_id)
        else:
            logger.warning(
                "async agent enqueue fn not wired; run left queued",
                extra={"run_id": run.run_id},
            )
        return AgentRunResponse.model_validate(run)

    def execute_async_run(self, run_id: str) -> None:
        """Execute a queued async run. Called by the background worker."""
        self.runtime_service.execute_async_run(run_id)

    def list_queued_run_ids(self, limit: int = 100) -> list[str]:
        """Return ids of runs still in ``queued`` status (worker reconciliation)."""
        return self.db_model_service.list_queued_run_ids(limit)

    def resume_agent_run_for_actor(
        self, actor: ActorContext, run_id: str, request: AgentResumeRequest
    ) -> AgentRunResponse:
        context = self._request_context(actor)
        run = self.runtime_service.resume(context, run_id, request)
        return AgentRunResponse.model_validate(run)

    def get_agent_run_for_actor(self, actor: ActorContext, run_id: str) -> AgentRunResponse:
        context = self._request_context(actor)
        run = self.runtime_service.get_run(context, run_id)
        return AgentRunResponse.model_validate(run)

    def list_agent_runs_for_actor(
        self,
        actor: ActorContext,
        *,
        limit: int,
        offset: int,
        status: str | None = None,
        definition_id: str | None = None,
    ) -> AgentRunListResponse:
        context = self._request_context(actor)
        runs, total = self.runtime_service.list_runs(
            context,
            limit=limit,
            offset=offset,
            status=status,
            definition_id=definition_id,
        )
        return AgentRunListResponse(
            items=[AgentRunResponse.model_validate(run) for run in runs],
            total=total,
        )

    def list_trace_runs_for_actor(
        self,
        actor: ActorContext,
        *,
        limit: int,
        offset: int,
        status: str | None = None,
        agent_name: str | None = None,
        run_type: str | None = None,
        session_id: str | None = None,
    ) -> AgentTraceRunListResponse:
        context = self._request_context(actor)
        runs, total = self.db_model_service.list_trace_runs(
            context.organization_id,
            limit=limit,
            offset=offset,
            status=status,
            agent_name=agent_name,
            run_type=run_type,
            session_id=session_id,
        )
        return AgentTraceRunListResponse(
            items=[AgentTraceRunListItem.model_validate(run) for run in runs],
            total=total,
        )

    def list_trace_sessions_for_actor(
        self,
        actor: ActorContext,
        *,
        limit: int,
        offset: int,
        status: str | None = None,
        agent_name: str | None = None,
        run_type: str | None = None,
    ) -> AgentTraceSessionListResponse:
        context = self._request_context(actor)
        sessions, total = self.db_model_service.list_trace_sessions(
            context.organization_id,
            limit=limit,
            offset=offset,
            status=status,
            agent_name=agent_name,
            run_type=run_type,
        )
        return AgentTraceSessionListResponse(
            items=[AgentTraceSessionListItem.model_validate(session) for session in sessions],
            total=total,
        )

    def get_trace_run_for_actor(
        self,
        actor: ActorContext,
        run_id: str,
    ) -> AgentTraceRunDetailResponse:
        context = self._request_context(actor)
        run = self.db_model_service.get_trace_run(run_id, context.organization_id)
        if run is None:
            raise NotFoundError("agent trace run not found")
        if run.expires_at is not None and run.expires_at <= datetime.now(UTC):
            raise NotFoundError("agent trace run not found")
        events = self.db_model_service.list_trace_events(run.id)
        return AgentTraceRunDetailResponse(
            **AgentTraceRunListItem.model_validate(run).model_dump(),
            context=run.context,
            events=[AgentTraceEventResponse.model_validate(event) for event in events],
        )

    def list_sessions_for_actor(
        self,
        actor: ActorContext,
        *,
        limit: int,
        offset: int,
    ) -> list[AgentSessionResponse]:
        context = self._request_context(actor)
        sessions = self.db_model_service.list_sessions(
            context.user_id or "system",
            context.organization_id,
            limit=limit,
            offset=offset,
        )
        # include_agent_mode so an Agent Mode session resolves its display name
        # instead of rendering blank. This dict is only used for the name lookup
        # below; it never reaches the response.
        definitions = {
            definition.definition_id: definition
            for definition in self.definition_service.list_definitions(
                context, active_only=False, include_agent_mode=True
            )
        }
        return [
            AgentSessionResponse(
                session_id=session.session_id,
                definition_id=session.definition_id,
                agent_name=definitions.get(session.definition_id, {}).display_name
                if session.definition_id in definitions
                else None,
                title=session.title,
                context=session.context,
                message_count=session.message_count,
                total_tokens=session.total_tokens,
                created_at=session.created_at,
                updated_at=session.updated_at,
            )
            for session in sessions
        ]

    def get_session_for_actor(
        self, actor: ActorContext, session_id: str
    ) -> SessionWithMessagesResponse:
        context = self._request_context(actor)
        session = self.db_model_service.get_session(
            session_id,
            user_id=context.user_id or "system",
            organization_id=context.organization_id,
        )
        if session is None:
            raise NotFoundError("agent session not found")
        definition = (
            self.definition_service.get_definition(context, session.definition_id)
            if session.definition_id
            else None
        )
        messages = self.db_model_service.list_messages(session.session_id)
        return SessionWithMessagesResponse(
            session=AgentSessionResponse(
                session_id=session.session_id,
                definition_id=session.definition_id,
                agent_name=definition.display_name if definition else None,
                title=session.title,
                context=session.context,
                message_count=session.message_count,
                total_tokens=session.total_tokens,
                created_at=session.created_at,
                updated_at=session.updated_at,
            ),
            messages=[AgentMessageResponse.model_validate(message) for message in messages],
        )

    def delete_session_for_actor(self, actor: ActorContext, session_id: str) -> bool:
        context = self._request_context(actor)
        return self.db_model_service.delete_session(
            session_id,
            context.user_id or "system",
            context.organization_id,
        )

    def rename_session_for_actor(
        self, actor: ActorContext, session_id: str, title: str
    ) -> AgentSessionResponse:
        context = self._request_context(actor)
        # Authorize via the user+org-scoped get_session BEFORE the unscoped
        # update_session, so a session can only be renamed by its owner org/user.
        session = self.db_model_service.get_session(
            session_id,
            user_id=context.user_id or "system",
            organization_id=context.organization_id,
        )
        if session is None:
            raise NotFoundError("agent session not found")
        updated = self.db_model_service.update_session(session_id, title=title) or session
        definition = (
            self.definition_service.get_definition(context, updated.definition_id)
            if updated.definition_id
            else None
        )
        return AgentSessionResponse(
            session_id=updated.session_id,
            definition_id=updated.definition_id,
            agent_name=definition.display_name if definition else None,
            title=updated.title,
            context=updated.context,
            message_count=updated.message_count,
            total_tokens=updated.total_tokens,
            created_at=updated.created_at,
            updated_at=updated.updated_at,
        )

    def cancel_agent_run_for_actor(self, actor: ActorContext, run_id: str) -> AgentRunResponse:
        context = self._request_context(actor)
        run = self.runtime_service.cancel_run(context, run_id)
        return AgentRunResponse.model_validate(run)

    def _request_context(self, actor: ActorContext) -> RequestContext:
        organization_id = self._require_actor_field(actor, "organization_id")
        roles_value = actor.get("roles")
        roles = [str(role) for role in roles_value] if isinstance(roles_value, list) else []
        return RequestContext(
            organization_id=organization_id,
            user_id=actor_str(actor, "user_id") or None,
            roles=roles,
            request_id=actor_str(actor, "request_id") or None,
            source="api",
        )

    @staticmethod
    def _require_actor_field(actor: ActorContext, field_name: str) -> str:
        value = actor_str(actor, field_name)
        if not value:
            raise ValidationError(f"Missing actor field: {field_name}")
        return value
