"""Deterministic context assembly for phase-1 agent runs."""

from __future__ import annotations

from typing import Any

from agent.models.interface import (
    AgentExecutionContext,
    AgentSessionContext,
    DomainContext,
    RequestContext,
    RuntimeContext,
)
from exceptions import NotFoundError, ValidationError


class AgentContextService:
    """Build explicit runtime, session, domain, and memory context layers."""

    def __init__(self, agent_model_service, *, max_recent_messages: int = 10) -> None:
        self.agent_model_service = agent_model_service
        self.max_recent_messages = max_recent_messages

    def build_context(
        self,
        context: RequestContext,
        *,
        session_id: str | None = None,
        request_context: dict[str, Any] | None = None,
    ) -> AgentExecutionContext:
        """Assemble the full execution context from request and optional session.

        Args:
            context: Authenticated request context (tenant, user, roles).
            session_id: Optional session whose recent messages are loaded.
            request_context: Optional caller-supplied domain context payload.

        Returns:
            A fully assembled AgentExecutionContext with runtime, session,
            domain, and (currently empty) memory layers.
        """
        session_context = self.load_session_context(context, session_id) if session_id else None
        domain = self.load_domain_context(request_context or {})
        return AgentExecutionContext(
            request=context,
            runtime=RuntimeContext(
                organization_id=context.organization_id,
                user_id=context.user_id,
                roles=list(context.roles),
                request_id=context.request_id,
                source=context.source,
            ),
            session=session_context,
            domain=domain,
            memory=None,
        )

    def load_session_context(self, context: RequestContext, session_id: str) -> AgentSessionContext:
        """Load a tenant-scoped session and its most recent messages.

        Args:
            context: Authenticated request context used to scope the lookup.
            session_id: Identifier of the session to load.

        Returns:
            An AgentSessionContext with up to ``max_recent_messages`` messages.

        Raises:
            NotFoundError: If the session does not exist for this tenant/user.
        """
        session = self.agent_model_service.get_session(
            session_id,
            user_id=context.user_id,
            organization_id=context.organization_id,
        )
        if session is None:
            raise NotFoundError("agent session not found")
        messages = self.agent_model_service.list_messages(session_id)
        recent_messages = [
            {
                "message_id": message.message_id,
                "role": message.role,
                "content": message.content,
                "created_at": message.created_at.isoformat(),
            }
            for message in messages[-self.max_recent_messages :]
        ]
        return AgentSessionContext(
            session_id=session.session_id,
            definition_id=session.definition_id,
            recent_messages=recent_messages,
            context=session.context,
        )

    @staticmethod
    def load_domain_context(request_context: dict[str, Any]) -> DomainContext:
        """Build a DomainContext from a caller-supplied payload.

        Only the keys ``entities``, ``workflow_state``, ``audit_events`` and
        ``allowed_actions`` are permitted; any other key raises ValidationError
        so callers cannot smuggle arbitrary data into the execution context.

        Args:
            request_context: Caller-supplied domain payload.

        Returns:
            A normalized DomainContext.

        Raises:
            ValidationError: If unsupported keys are present.
        """
        allowed_keys = {"entities", "workflow_state", "audit_events", "allowed_actions"}
        unexpected_keys = sorted(set(request_context) - allowed_keys)
        if unexpected_keys:
            raise ValidationError(f"Unsupported agent context keys: {', '.join(unexpected_keys)}")
        return DomainContext(
            entities=list(request_context.get("entities") or []),
            workflow_state=dict(request_context.get("workflow_state") or {}),
            audit_events=list(request_context.get("audit_events") or []),
            allowed_actions=list(request_context.get("allowed_actions") or []),
        )

    @staticmethod
    def summarize_context(execution_context: AgentExecutionContext) -> dict[str, Any]:
        return {
            "request": execution_context.request.model_dump(),
            "runtime": execution_context.runtime.model_dump(),
            "session": execution_context.session.model_dump()
            if execution_context.session
            else None,
            "domain": execution_context.domain.model_dump(),
            "memory": execution_context.memory,
        }
