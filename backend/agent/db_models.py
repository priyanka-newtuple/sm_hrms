"""Persistence adapters for agent state and traces."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.sql import func
from sqlalchemy.types import JSON

from agent.models.interface import (
    AgentDefinitionContract,
    AgentMessageContract,
    AgentRunContract,
    AgentSessionContract,
    AgentTraceEventContract,
    AgentTraceRunContract,
    AgentTraceSessionContract,
)
from common.logger import logger
from database.manager import Base
from exceptions import PersistenceError


# region ORM Models
class AgentDefinitionModel(Base):
    __tablename__ = "agent_definitions"

    definition_id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name = Column(String(64), nullable=False)
    display_name = Column(String(128), nullable=False)
    description = Column(String(512), nullable=True)
    system_prompt = Column(Text, nullable=False)
    allowed_tools = Column(JSON, nullable=True)
    constraints = Column(JSON, nullable=False, default=dict)
    suggestions = Column(JSON, nullable=False, default=list)
    model_override = Column(String(128), nullable=True)
    is_active = Column(Integer, nullable=False, default=1)
    is_system = Column(Integer, nullable=False, default=0)
    organization_id = Column(String(36), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_agent_definitions_org_name", "organization_id", "name", unique=True),
    )


class AgentSessionModel(Base):
    __tablename__ = "agent_sessions"

    session_id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    definition_id = Column(
        String(36),
        ForeignKey("agent_definitions.definition_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id = Column(String(36), nullable=False, index=True)
    organization_id = Column(String(36), nullable=False, index=True)
    context = Column(JSON, nullable=True)
    title = Column(String(256), nullable=True)
    total_tokens = Column(Integer, nullable=False, default=0)
    message_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_agent_sessions_user_updated", "user_id", "updated_at"),)


class AgentMessageModel(Base):
    __tablename__ = "agent_messages"

    message_id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id = Column(
        String(36),
        ForeignKey("agent_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)
    tool_calls = Column(JSON, nullable=True)
    pending_actions = Column(JSON, nullable=True)
    tokens_used = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_agent_messages_session_created", "session_id", "created_at"),)


class AgentRunModel(Base):
    __tablename__ = "agent_runs"

    run_id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id = Column(String(36), nullable=False, index=True)
    definition_id = Column(
        String(36),
        ForeignKey("agent_definitions.definition_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    session_id = Column(
        String(36),
        ForeignKey("agent_sessions.session_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id = Column(String(36), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="queued")
    input_text = Column(Text, nullable=False)
    output_text = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    backend_metadata = Column(JSON, nullable=False, default=dict)
    execution_context = Column(JSON, nullable=False, default=dict)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_agent_runs_org_created", "organization_id", "created_at"),
        Index("ix_agent_runs_org_status", "organization_id", "status"),
    )


class AgentTraceRunModel(Base):
    __tablename__ = "agent_trace_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id = Column(String(36), nullable=False, index=True)
    user_id = Column(String(36), nullable=True, index=True)
    agent_name = Column(String(128), nullable=False, index=True)
    run_type = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False)
    model = Column(String(128), nullable=True)
    input_message = Column(Text, nullable=True)
    session_id = Column(String(36), nullable=True, index=True)
    message_id = Column(String(36), nullable=True, index=True)
    context = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    tokens_used = Column(Integer, nullable=False, default=0)
    iterations = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_agent_trace_runs_org_started", "organization_id", "started_at"),
        Index("ix_agent_trace_runs_org_status", "organization_id", "status"),
    )


class AgentTraceEventModel(Base):
    __tablename__ = "agent_trace_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id = Column(
        String(36),
        ForeignKey("agent_trace_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    seq = Column(Integer, nullable=False)
    kind = Column(String(64), nullable=False, index=True)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_agent_trace_events_run_seq", "run_id", "seq"),)


# endregion ORM Models


class AgentModelService:
    """Persist agent definitions, sessions, messages, and traces in PostgreSQL."""

    def __init__(self, database_service_manager) -> None:
        """Store database dependencies for the agent persistence layer.

        Args:
            database_service_manager: Shared database service manager with PostgreSQL access.

        Returns:
            `None`.
        """
        super().__init__()
        if database_service_manager is None or not hasattr(
            database_service_manager, "postgres_db_service"
        ):
            raise PersistenceError("Database service manager is required for AgentModelService")

        self.current_db = database_service_manager.postgres_db_service()
        if self.current_db is None or getattr(self.current_db, "engine", None) is None:
            raise PersistenceError(
                "PostgreSQL database service is not configured for AgentModelService"
            )

        self.current_db_engine = self.current_db.engine

    # region Definition Persistence
    def list_definitions(
        self, organization_id: str, active_only: bool = True
    ) -> list[AgentDefinitionContract]:
        """List agent definitions for an organization.

        Args:
            organization_id: Organization scope to query.
            active_only: Whether to limit results to active definitions.

        Returns:
            Definition contracts ordered by display name.
        """
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                query = db.query(AgentDefinitionModel).filter(
                    AgentDefinitionModel.organization_id == organization_id
                )
                if active_only:
                    query = query.filter(AgentDefinitionModel.is_active == 1)
                rows = query.order_by(AgentDefinitionModel.display_name.asc()).all()
                return [AgentDefinitionContract.model_validate(row) for row in rows]
        except Exception as exc:
            raise PersistenceError(f"Unable to list definitions: {exc}") from exc

    def get_definition(
        self, definition_id: str, organization_id: str
    ) -> AgentDefinitionContract | None:
        """Fetch one agent definition by identifier and organization.

        Args:
            definition_id: Unique agent definition identifier.
            organization_id: Organization scope to query.

        Returns:
            The matching definition contract, or `None` when no definition exists.
        """
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                row = (
                    db.query(AgentDefinitionModel)
                    .filter(
                        AgentDefinitionModel.definition_id == definition_id,
                        AgentDefinitionModel.organization_id == organization_id,
                    )
                    .first()
                )
                return AgentDefinitionContract.model_validate(row) if row else None
        except Exception as exc:
            raise PersistenceError(f"Unable to fetch definition {definition_id}: {exc}") from exc

    def get_definition_by_name(
        self, organization_id: str, name: str, active_only: bool = True
    ) -> AgentDefinitionContract | None:
        """Fetch one agent definition by name and organization.

        Args:
            organization_id: Organization scope to query.
            name: Stable agent definition name.
            active_only: Whether to limit results to active definitions.

        Returns:
            The matching definition contract, or `None` when no definition exists.
        """
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                query = db.query(AgentDefinitionModel).filter(
                    AgentDefinitionModel.organization_id == organization_id,
                    AgentDefinitionModel.name == name,
                )
                if active_only:
                    query = query.filter(AgentDefinitionModel.is_active == 1)
                row = query.first()
                return AgentDefinitionContract.model_validate(row) if row else None
        except Exception as exc:
            raise PersistenceError(f"Unable to fetch definition named {name}: {exc}") from exc

    def create_definition(
        self, organization_id: str, payload: dict[str, Any]
    ) -> AgentDefinitionContract:
        """Persist a new agent definition for an organization.

        Args:
            organization_id: Organization scope that owns the definition.
            payload: Normalized definition payload to persist.

        Returns:
            The persisted definition contract.
        """
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                now = datetime.now(UTC)
                created_at = payload.get("created_at") or now
                updated_at = payload.get("updated_at") or created_at
                model = AgentDefinitionModel(
                    definition_id=str(payload.get("definition_id") or uuid4()),
                    name=str(payload["name"]),
                    display_name=str(payload["display_name"]),
                    description=payload.get("description"),
                    system_prompt=str(payload["system_prompt"]),
                    allowed_tools=list(payload["allowed_tools"])
                    if payload.get("allowed_tools") is not None
                    else None,
                    constraints=dict(payload.get("constraints") or {}),
                    suggestions=list(payload.get("suggestions") or []),
                    model_override=payload.get("model_override"),
                    is_active=1 if payload.get("is_active", True) else 0,
                    is_system=1 if payload.get("is_system", False) else 0,
                    organization_id=organization_id,
                    created_at=created_at,
                    updated_at=updated_at,
                )
                db.add(model)
                db.commit()
                db.refresh(model)
                return AgentDefinitionContract.model_validate(model)
        except Exception as exc:
            raise PersistenceError(f"Unable to create definition: {exc}") from exc

    def update_definition(
        self, definition_id: str, organization_id: str, updates: dict[str, Any]
    ) -> AgentDefinitionContract | None:
        """Apply partial updates to an existing agent definition.

        Args:
            definition_id: Unique agent definition identifier.
            organization_id: Organization scope that owns the definition.
            updates: Partial update payload to apply.

        Returns:
            The updated definition contract, or `None` when no definition exists.
        """
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                row = (
                    db.query(AgentDefinitionModel)
                    .filter(
                        AgentDefinitionModel.definition_id == definition_id,
                        AgentDefinitionModel.organization_id == organization_id,
                    )
                    .first()
                )
                if row is None:
                    return None
                for key, value in updates.items():
                    if key == "constraints" and value is not None:
                        row.constraints = dict(value)
                    elif key == "suggestions" and value is not None:
                        row.suggestions = list(value)
                    elif key == "allowed_tools":
                        row.allowed_tools = list(value) if value is not None else None
                    else:
                        setattr(row, key, value)
                row.updated_at = datetime.now(UTC)
                db.commit()
                db.refresh(row)
                return AgentDefinitionContract.model_validate(row)
        except Exception as exc:
            raise PersistenceError(f"Unable to update definition {definition_id}: {exc}") from exc

    def delete_definition(self, definition_id: str, organization_id: str) -> bool:
        """Delete an agent definition by identifier and organization.

        Args:
            definition_id: Unique agent definition identifier.
            organization_id: Organization scope that owns the definition.

        Returns:
            `True` when a definition was deleted, otherwise `False`.
        """
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                row = (
                    db.query(AgentDefinitionModel)
                    .filter(
                        AgentDefinitionModel.definition_id == definition_id,
                        AgentDefinitionModel.organization_id == organization_id,
                    )
                    .first()
                )
                if row is None:
                    return False
                db.delete(row)
                db.commit()
                return True
        except Exception as exc:
            raise PersistenceError(f"Unable to delete definition {definition_id}: {exc}") from exc

    # endregion Definition Persistence

    # region Session Persistence
    def create_session(
        self, definition_id: str | None, user_id: str, organization_id: str, context: dict | None
    ) -> AgentSessionContract:
        """Create a new persisted chat session.

        Args:
            definition_id: Optional agent definition identifier bound to the session.
            user_id: User that owns the session.
            organization_id: Organization scope that owns the session.
            context: Optional session context payload.

        Returns:
            The persisted session contract.
        """
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                now = datetime.now(UTC)
                model = AgentSessionModel(
                    session_id=str(uuid4()),
                    definition_id=definition_id,
                    user_id=user_id,
                    organization_id=organization_id,
                    context=context,
                    title=None,
                    total_tokens=0,
                    message_count=0,
                    created_at=now,
                    updated_at=now,
                )
                db.add(model)
                db.commit()
                db.refresh(model)
                return AgentSessionContract.model_validate(model)
        except Exception as exc:
            raise PersistenceError(f"Unable to create session: {exc}") from exc

    def get_session(
        self, session_id: str, user_id: str | None = None, organization_id: str | None = None
    ) -> AgentSessionContract | None:
        """Fetch one session with optional user and organization scoping.

        Args:
            session_id: Unique session identifier.
            user_id: Optional owner filter for the session.
            organization_id: Optional organization filter for the session.

        Returns:
            The matching session contract, or `None` when no session exists.
        """
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                query = db.query(AgentSessionModel).filter(
                    AgentSessionModel.session_id == session_id
                )
                if user_id:
                    query = query.filter(AgentSessionModel.user_id == user_id)
                if organization_id:
                    query = query.filter(AgentSessionModel.organization_id == organization_id)
                row = query.first()
                return AgentSessionContract.model_validate(row) if row else None
        except Exception as exc:
            raise PersistenceError(f"Unable to fetch session {session_id}: {exc}") from exc

    def list_sessions(
        self, user_id: str, organization_id: str, limit: int, offset: int
    ) -> list[AgentSessionContract]:
        """List persisted sessions for a user in one organization.

        Args:
            user_id: User that owns the sessions.
            organization_id: Organization that owns the sessions.
            limit: Maximum number of sessions to return.
            offset: Pagination offset.

        Returns:
            Session contracts ordered by most recent update time.
        """
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                rows = (
                    db.query(AgentSessionModel)
                    .filter(
                        AgentSessionModel.user_id == user_id,
                        AgentSessionModel.organization_id == organization_id,
                    )
                    .order_by(AgentSessionModel.updated_at.desc())
                    .offset(offset)
                    .limit(limit)
                    .all()
                )
                return [AgentSessionContract.model_validate(row) for row in rows]
        except Exception as exc:
            raise PersistenceError(
                f"Unable to list sessions for user {user_id} in organization {organization_id}: {exc}"
            ) from exc

    def update_session(
        self,
        session_id: str,
        *,
        context: dict | None = None,
        title: str | None = None,
        token_delta: int = 0,
        message_delta: int = 0,
    ) -> AgentSessionContract | None:
        """Update session metadata and usage counters.

        Args:
            session_id: Unique session identifier.
            context: Optional replacement session context payload.
            title: Optional session title.
            token_delta: Token count increment to apply.
            message_delta: Message count increment to apply.

        Returns:
            The updated session contract, or `None` when no session exists.
        """
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                row = (
                    db.query(AgentSessionModel)
                    .filter(AgentSessionModel.session_id == session_id)
                    .first()
                )
                if row is None:
                    return None
                if context is not None:
                    row.context = dict(context)
                if title is not None:
                    row.title = title
                row.total_tokens += token_delta
                row.message_count += message_delta
                row.updated_at = datetime.now(UTC)
                db.commit()
                db.refresh(row)
                return AgentSessionContract.model_validate(row)
        except Exception as exc:
            raise PersistenceError(f"Unable to update session {session_id}: {exc}") from exc

    def delete_session(self, session_id: str, user_id: str, organization_id: str) -> bool:
        """Delete a persisted session and its messages for a user in one organization.

        Args:
            session_id: Unique session identifier.
            user_id: User that owns the session.
            organization_id: Organization that owns the session.

        Returns:
            `True` when a session was deleted, otherwise `False`.
        """
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                row = (
                    db.query(AgentSessionModel)
                    .filter(
                        AgentSessionModel.session_id == session_id,
                        AgentSessionModel.user_id == user_id,
                        AgentSessionModel.organization_id == organization_id,
                    )
                    .first()
                )
                if row is None:
                    return False
                db.delete(row)
                db.commit()
                return True
        except Exception as exc:
            raise PersistenceError(
                f"Unable to delete session {session_id} in organization {organization_id}: {exc}"
            ) from exc

    # endregion Session Persistence

    # region Message Persistence
    def create_message(
        self,
        *,
        session_id: str,
        role: str,
        content: str,
        tool_calls: list[dict] | None = None,
        pending_actions: list[dict] | None = None,
        tokens_used: int = 0,
    ) -> AgentMessageContract:
        """Persist a single chat message for a session.

        Args:
            session_id: Session that owns the message.
            role: Message role such as `user` or `agent`.
            content: Serialized message content.
            tool_calls: Optional tool call records attached to the message.
            pending_actions: Optional pending action records attached to the message.
            tokens_used: Token usage attributed to the message.

        Returns:
            The persisted message contract.
        """
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                model = AgentMessageModel(
                    message_id=str(uuid4()),
                    session_id=session_id,
                    role=role,
                    content=content,
                    tool_calls=tool_calls,
                    pending_actions=pending_actions,
                    tokens_used=tokens_used,
                    created_at=datetime.now(UTC),
                )
                db.add(model)
                db.commit()
                db.refresh(model)
                return AgentMessageContract.model_validate(model)
        except Exception as exc:
            raise PersistenceError(
                f"Unable to create message for session {session_id}: {exc}"
            ) from exc

    def get_message(self, message_id: str) -> AgentMessageContract | None:
        """Fetch one persisted message by identifier.

        Args:
            message_id: Unique message identifier.

        Returns:
            The matching message contract, or `None` when no message exists.
        """
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                row = (
                    db.query(AgentMessageModel)
                    .filter(AgentMessageModel.message_id == message_id)
                    .first()
                )
                return AgentMessageContract.model_validate(row) if row else None
        except Exception as exc:
            raise PersistenceError(f"Unable to fetch message {message_id}: {exc}") from exc

    def list_messages(self, session_id: str) -> list[AgentMessageContract]:
        """List session messages ordered by creation time.

        Args:
            session_id: Session that owns the messages.

        Returns:
            Message contracts ordered by creation time.
        """
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                rows = (
                    db.query(AgentMessageModel)
                    .filter(AgentMessageModel.session_id == session_id)
                    .order_by(AgentMessageModel.created_at.asc())
                    .all()
                )
                return [AgentMessageContract.model_validate(row) for row in rows]
        except Exception as exc:
            raise PersistenceError(
                f"Unable to list messages for session {session_id}: {exc}"
            ) from exc

    def update_pending_action(
        self, message_id: str, action_id: str, updates: dict[str, Any]
    ) -> AgentMessageContract | None:
        """Apply an update to one pending action embedded in a message.

        Args:
            message_id: Message that contains the pending action.
            action_id: Pending action identifier to update.
            updates: Partial action payload to merge.

        Returns:
            The updated message contract, or `None` when no matching action exists.
        """
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                row = (
                    db.query(AgentMessageModel)
                    .filter(AgentMessageModel.message_id == message_id)
                    .first()
                )
                if row is None or not row.pending_actions:
                    return None
                updated_actions: list[dict] = []
                updated = False
                for action in row.pending_actions:
                    if action.get("action_id") == action_id:
                        merged = dict(action)
                        merged.update(updates)
                        updated_actions.append(merged)
                        updated = True
                        continue
                    updated_actions.append(action)
                if not updated:
                    return None
                row.pending_actions = updated_actions
                db.commit()
                db.refresh(row)
                return AgentMessageContract.model_validate(row)
        except Exception as exc:
            raise PersistenceError(f"Unable to update pending action {action_id}: {exc}") from exc

    # endregion Message Persistence

    # region Run Persistence
    def create_run(self, payload: dict[str, Any]) -> AgentRunContract:
        """Persist a new agent runtime record before execution starts."""
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                now = datetime.now(UTC)
                model = AgentRunModel(
                    run_id=str(payload.get("run_id") or uuid4()),
                    organization_id=str(payload["organization_id"]),
                    definition_id=str(payload["definition_id"]),
                    session_id=payload.get("session_id"),
                    user_id=payload.get("user_id"),
                    status=str(payload.get("status") or "queued"),
                    input_text=str(payload["input_text"]),
                    output_text=payload.get("output_text"),
                    error=payload.get("error"),
                    backend_metadata=dict(payload.get("backend_metadata") or {}),
                    execution_context=dict(payload.get("execution_context") or {}),
                    started_at=payload.get("started_at"),
                    completed_at=payload.get("completed_at"),
                    created_at=payload.get("created_at") or now,
                    updated_at=payload.get("updated_at") or now,
                )
                db.add(model)
                db.commit()
                db.refresh(model)
                return AgentRunContract.model_validate(model)
        except Exception as exc:
            raise PersistenceError(f"Unable to create agent run: {exc}") from exc

    def update_run(
        self, run_id: str, organization_id: str, updates: dict[str, Any]
    ) -> AgentRunContract | None:
        """Apply partial updates to one tenant-scoped agent run."""
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                row = (
                    db.query(AgentRunModel)
                    .filter(
                        AgentRunModel.run_id == run_id,
                        AgentRunModel.organization_id == organization_id,
                    )
                    .first()
                )
                if row is None:
                    return None
                for key, value in updates.items():
                    if key in {"backend_metadata", "execution_context"} and value is not None:
                        setattr(row, key, dict(value))
                    else:
                        setattr(row, key, value)
                row.updated_at = datetime.now(UTC)
                db.commit()
                db.refresh(row)
                return AgentRunContract.model_validate(row)
        except Exception as exc:
            raise PersistenceError(f"Unable to update agent run {run_id}: {exc}") from exc

    def get_run(self, run_id: str, organization_id: str) -> AgentRunContract | None:
        """Fetch one run by identifier and organization."""
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                row = (
                    db.query(AgentRunModel)
                    .filter(
                        AgentRunModel.run_id == run_id,
                        AgentRunModel.organization_id == organization_id,
                    )
                    .first()
                )
                return AgentRunContract.model_validate(row) if row else None
        except Exception as exc:
            raise PersistenceError(f"Unable to fetch agent run {run_id}: {exc}") from exc

    def list_runs(
        self,
        organization_id: str,
        *,
        limit: int,
        offset: int,
        status: str | None = None,
        definition_id: str | None = None,
    ) -> tuple[list[AgentRunContract], int]:
        """List tenant-scoped agent runs ordered by creation time."""
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                query = db.query(AgentRunModel).filter(
                    AgentRunModel.organization_id == organization_id
                )
                if status:
                    query = query.filter(AgentRunModel.status == status)
                if definition_id:
                    query = query.filter(AgentRunModel.definition_id == definition_id)
                total = query.count()
                rows = (
                    query.order_by(AgentRunModel.created_at.desc())
                    .offset(offset)
                    .limit(limit)
                    .all()
                )
                return [AgentRunContract.model_validate(row) for row in rows], total
        except Exception as exc:
            raise PersistenceError(f"Unable to list agent runs: {exc}") from exc

    def get_run_by_id(self, run_id: str) -> AgentRunContract | None:
        """Fetch one run by identifier without an organization filter.

        Intended for the trusted background worker, which only holds the run id
        when it dequeues an async agent run. Every subsequent write still goes
        through the org-scoped ``update_run`` using the row's own
        ``organization_id``, so tenant isolation on writes is preserved.
        """
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                row = db.query(AgentRunModel).filter(AgentRunModel.run_id == run_id).first()
                return AgentRunContract.model_validate(row) if row else None
        except Exception as exc:
            logger.exception("Unable to fetch agent run", extra={"run_id": run_id})
            raise PersistenceError(f"Unable to fetch agent run {run_id}: {exc}") from exc

    def list_queued_run_ids(self, limit: int = 100) -> list[str]:
        """Return ids of runs still in ``queued`` status across all tenants.

        Used by the worker on startup to re-enqueue async agent runs that were
        persisted but never drained (e.g. enqueued while no worker was running).
        """
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                rows = (
                    db.query(AgentRunModel.run_id)
                    .filter(AgentRunModel.status == "queued")
                    .order_by(AgentRunModel.created_at.asc())
                    .limit(limit)
                    .all()
                )
                return [str(row[0]) for row in rows]
        except Exception as exc:
            logger.exception("Unable to list queued agent runs")
            raise PersistenceError(f"Unable to list queued agent runs: {exc}") from exc

    # endregion Run Persistence

    # region Trace Persistence
    def persist_trace(self, run_data: dict, events: list[dict]) -> AgentTraceRunContract:
        """Persist a trace run together with its ordered events.

        Args:
            run_data: Normalized trace run payload.
            events: Ordered trace event payloads to persist with the run.

        Returns:
            The persisted trace run contract.
        """
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                now = datetime.now(UTC)
                model = AgentTraceRunModel(
                    id=str(run_data.get("id") or uuid4()),
                    organization_id=str(run_data["organization_id"]),
                    user_id=run_data.get("user_id"),
                    agent_name=str(run_data["agent_name"]),
                    run_type=str(run_data["run_type"]),
                    status=str(run_data["status"]),
                    model=run_data.get("model"),
                    input_message=run_data.get("input_message"),
                    session_id=run_data.get("session_id"),
                    message_id=run_data.get("message_id"),
                    context=dict(run_data.get("context") or {})
                    if run_data.get("context") is not None
                    else None,
                    error=run_data.get("error"),
                    tokens_used=int(run_data.get("tokens_used") or 0),
                    iterations=run_data.get("iterations"),
                    duration_ms=run_data.get("duration_ms"),
                    started_at=run_data.get("started_at") or now,
                    completed_at=run_data.get("completed_at"),
                    expires_at=run_data.get("expires_at"),
                    created_at=run_data.get("created_at") or now,
                    updated_at=run_data.get("updated_at") or now,
                )
                db.add(model)
                db.flush()
                for event in events:
                    db.add(
                        AgentTraceEventModel(
                            id=str(uuid4()),
                            run_id=model.id,
                            seq=int(event.get("seq", 0)),
                            kind=str(event.get("kind", "event")),
                            payload=dict(event.get("payload") or {}),
                        )
                    )
                db.commit()
                db.refresh(model)
                contract = AgentTraceRunContract.model_validate(model)
            self.delete_expired_traces(now)
            return contract
        except Exception as exc:
            raise PersistenceError(f"Unable to persist trace run: {exc}") from exc

    def list_trace_runs(
        self,
        organization_id: str,
        *,
        limit: int,
        offset: int,
        status: str | None = None,
        agent_name: str | None = None,
        run_type: str | None = None,
        session_id: str | None = None,
    ) -> tuple[list[AgentTraceRunContract], int]:
        """List trace runs for an organization with optional filters.

        Args:
            organization_id: Organization scope to query.
            limit: Maximum number of trace runs to return.
            offset: Pagination offset.
            status: Optional status filter.
            agent_name: Optional agent-name filter.
            run_type: Optional run-type filter.

        Returns:
            A tuple of filtered trace-run contracts and the total count.
        """
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                query = db.query(AgentTraceRunModel).filter(
                    AgentTraceRunModel.organization_id == organization_id
                )
                query = query.filter(
                    (AgentTraceRunModel.expires_at.is_(None))
                    | (AgentTraceRunModel.expires_at > datetime.now(UTC))
                )
                if status:
                    query = query.filter(AgentTraceRunModel.status == status)
                if agent_name:
                    query = query.filter(AgentTraceRunModel.agent_name == agent_name)
                if run_type:
                    query = query.filter(AgentTraceRunModel.run_type == run_type)
                if session_id:
                    query = query.filter(AgentTraceRunModel.session_id == session_id)
                total = query.count()
                rows = (
                    query.order_by(AgentTraceRunModel.started_at.desc())
                    .offset(offset)
                    .limit(limit)
                    .all()
                )
                return [AgentTraceRunContract.model_validate(row) for row in rows], total
        except Exception as exc:
            raise PersistenceError(f"Unable to list trace runs: {exc}") from exc

    def list_trace_sessions(
        self,
        organization_id: str,
        *,
        limit: int,
        offset: int,
        status: str | None = None,
        agent_name: str | None = None,
        run_type: str | None = None,
    ) -> tuple[list[AgentTraceSessionContract], int]:
        """List grouped trace sessions for an organization with optional filters."""
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                session_key = func.coalesce(AgentTraceRunModel.session_id, AgentTraceRunModel.id)
                partition = [session_key]
                query = db.query(
                    session_key.label("session_key"),
                    AgentTraceRunModel.organization_id.label("organization_id"),
                    AgentTraceRunModel.user_id.label("user_id"),
                    AgentTraceRunModel.agent_name.label("agent_name"),
                    AgentTraceRunModel.id.label("latest_run_id"),
                    AgentTraceRunModel.message_id.label("latest_message_id"),
                    AgentTraceRunModel.status.label("latest_status"),
                    AgentTraceRunModel.input_message.label("latest_input_message"),
                    AgentTraceRunModel.model.label("model"),
                    func.count(AgentTraceRunModel.id)
                    .over(partition_by=partition)
                    .label("run_count"),
                    func.coalesce(
                        func.sum(AgentTraceRunModel.tokens_used).over(partition_by=partition),
                        0,
                    ).label("total_tokens"),
                    func.coalesce(
                        func.sum(AgentTraceRunModel.duration_ms).over(partition_by=partition),
                        0,
                    ).label("total_duration_ms"),
                    func.min(AgentTraceRunModel.started_at)
                    .over(partition_by=partition)
                    .label("first_started_at"),
                    AgentTraceRunModel.started_at.label("last_started_at"),
                    AgentTraceRunModel.completed_at.label("last_completed_at"),
                    func.row_number()
                    .over(
                        partition_by=partition,
                        order_by=(
                            AgentTraceRunModel.started_at.desc(),
                            AgentTraceRunModel.created_at.desc(),
                            AgentTraceRunModel.id.desc(),
                        ),
                    )
                    .label("rn"),
                ).filter(AgentTraceRunModel.organization_id == organization_id)
                query = query.filter(
                    (AgentTraceRunModel.expires_at.is_(None))
                    | (AgentTraceRunModel.expires_at > datetime.now(UTC))
                )
                if status:
                    query = query.filter(AgentTraceRunModel.status == status)
                if agent_name:
                    query = query.filter(AgentTraceRunModel.agent_name == agent_name)
                if run_type:
                    query = query.filter(AgentTraceRunModel.run_type == run_type)

                ranked = query.subquery()
                latest_query = db.query(ranked).filter(ranked.c.rn == 1)
                total = latest_query.count()
                rows = (
                    latest_query.order_by(ranked.c.last_started_at.desc())
                    .offset(offset)
                    .limit(limit)
                    .all()
                )
                return [
                    AgentTraceSessionContract(
                        session_id=row.session_key,
                        organization_id=row.organization_id,
                        user_id=row.user_id,
                        agent_name=row.agent_name,
                        latest_run_id=row.latest_run_id,
                        latest_message_id=row.latest_message_id,
                        latest_status=row.latest_status,
                        latest_input_message=row.latest_input_message,
                        model=row.model,
                        run_count=int(row.run_count or 0),
                        total_tokens=int(row.total_tokens or 0),
                        total_duration_ms=int(row.total_duration_ms or 0),
                        first_started_at=row.first_started_at,
                        last_started_at=row.last_started_at,
                        last_completed_at=row.last_completed_at,
                    )
                    for row in rows
                ], total
        except Exception as exc:
            raise PersistenceError(f"Unable to list trace sessions: {exc}") from exc

    def get_trace_run(self, run_id: str, organization_id: str) -> AgentTraceRunContract | None:
        """Fetch one trace run by identifier and organization.

        Args:
            run_id: Unique trace run identifier.
            organization_id: Organization scope to query.

        Returns:
            The matching trace run contract, or `None` when no run exists.
        """
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                row = (
                    db.query(AgentTraceRunModel)
                    .filter(
                        AgentTraceRunModel.id == run_id,
                        AgentTraceRunModel.organization_id == organization_id,
                        (AgentTraceRunModel.expires_at.is_(None))
                        | (AgentTraceRunModel.expires_at > datetime.now(UTC)),
                    )
                    .first()
                )
                return AgentTraceRunContract.model_validate(row) if row else None
        except Exception as exc:
            raise PersistenceError(f"Unable to fetch trace run {run_id}: {exc}") from exc

    def list_trace_events(self, run_id: str) -> list[AgentTraceEventContract]:
        """List persisted trace events for one trace run.

        Args:
            run_id: Trace run that owns the events.

        Returns:
            Trace event contracts ordered by sequence number.
        """
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                rows = (
                    db.query(AgentTraceEventModel)
                    .filter(AgentTraceEventModel.run_id == run_id)
                    .order_by(AgentTraceEventModel.seq.asc())
                    .all()
                )
                return [AgentTraceEventContract.model_validate(row) for row in rows]
        except Exception as exc:
            raise PersistenceError(f"Unable to list trace events for run {run_id}: {exc}") from exc

    def delete_expired_traces(self, cutoff: datetime) -> None:
        """Delete trace runs and events that expired before the cutoff.

        Args:
            cutoff: Expiration cutoff timestamp.

        Returns:
            `None`.
        """
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                expired_rows = (
                    db.query(AgentTraceRunModel)
                    .filter(AgentTraceRunModel.expires_at < cutoff)
                    .all()
                )
                for row in expired_rows:
                    db.delete(row)
                db.commit()
        except Exception as exc:
            raise PersistenceError(f"Unable to delete expired traces: {exc}") from exc

    # endregion Trace Persistence
