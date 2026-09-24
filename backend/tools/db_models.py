"""Persistence adapters for shared tool execution history."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text
from sqlalchemy.sql import func
from sqlalchemy.types import JSON

from database.manager import Base
from exceptions import PersistenceError

from tools.models.interface import ToolExecutionLogContract


# region ORM Models
class ToolExecutionLogModel(Base):
    """Persist one audit log row for a shared tool execution."""

    __tablename__ = "tool_execution_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id = Column(String(36), nullable=False, index=True)
    user_id = Column(String(36), nullable=True, index=True)
    actor_id = Column(String(36), nullable=True, index=True)
    actor_type = Column(String(32), nullable=True)
    source = Column(String(64), nullable=False, index=True)
    tool_name = Column(String(128), nullable=False, index=True)
    arguments = Column(JSON, nullable=False, default=dict)
    result = Column(JSON, nullable=False, default=dict)
    success = Column(Boolean, nullable=False, default=False, index=True)
    error = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=False, default=0)
    execution_backend = Column(String(32), nullable=False, index=True)
    run_id = Column(String(36), nullable=True, index=True)
    session_id = Column(String(36), nullable=True, index=True)
    entity_id = Column(String(36), nullable=True, index=True)
    entity_type = Column(String(128), nullable=True, index=True)
    request_id = Column(String(64), nullable=True, index=True)
    metadata_json = Column("metadata", JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    __table_args__ = (
        Index("ix_tool_execution_logs_org_created", "organization_id", "created_at"),
    )


# endregion ORM Models


class ToolsModelService:
    """Persist shared tool execution audit rows in PostgreSQL."""

    def __init__(self, database_service_manager) -> None:  # noqa: ANN001
        """Store database dependencies for the tools persistence layer.

        Args:
            database_service_manager: Shared database service manager with PostgreSQL access.

        Returns:
            `None`.
        """
        super().__init__()
        if database_service_manager is None or not hasattr(database_service_manager, "postgres_db_service"):
            raise PersistenceError("Database service manager is required for ToolsModelService")

        self.current_db = database_service_manager.postgres_db_service()
        if self.current_db is None or getattr(self.current_db, "engine", None) is None:
            raise PersistenceError("PostgreSQL database service is not configured for ToolsModelService")

        self.current_db_engine = self.current_db.engine

    # region Execution Log Persistence
    @staticmethod
    def _json_safe(value: object) -> dict[str, object]:
        """Coerce a mapping into a JSON-serializable dict for a JSON column.

        Tool arguments and results may contain non-JSON-native values (e.g.
        ``datetime`` objects from entity records), which psycopg2 cannot encode.
        Round-tripping through ``json.dumps(default=str)`` converts those values
        to strings so the audit row can be persisted.
        """
        return json.loads(json.dumps(dict(value or {}), default=str))

    def create_execution_log(self, payload: dict[str, object]) -> ToolExecutionLogContract:
        """Persist one shared tool execution audit row.

        Args:
            payload: Normalized tool execution payload to persist.

        Returns:
            The persisted execution log contract.
        """
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                model = ToolExecutionLogModel(
                    id=str(payload.get("id") or uuid4()),
                    organization_id=str(payload["organization_id"]),
                    user_id=payload.get("user_id"),
                    actor_id=payload.get("actor_id"),
                    actor_type=payload.get("actor_type"),
                    source=str(payload.get("source") or "tools"),
                    tool_name=str(payload["tool_name"]),
                    arguments=self._json_safe(payload.get("arguments")),
                    result=self._json_safe(payload.get("result")),
                    success=bool(payload.get("success", False)),
                    error=payload.get("error"),
                    duration_ms=int(payload.get("duration_ms") or 0),
                    execution_backend=str(payload.get("execution_backend") or "unknown"),
                    run_id=payload.get("run_id"),
                    session_id=payload.get("session_id"),
                    entity_id=payload.get("entity_id"),
                    entity_type=payload.get("entity_type"),
                    request_id=payload.get("request_id"),
                    metadata_json=self._json_safe(payload.get("metadata")),
                    created_at=payload.get("created_at") or datetime.now(timezone.utc),
                )
                db.add(model)
                db.commit()
                db.refresh(model)
                return ToolExecutionLogContract.model_validate(model)
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(f"Unable to create tool execution log: {exc}") from exc

    def list_execution_logs(
        self,
        organization_id: str,
        *,
        limit: int,
        offset: int,
        tool_name: str | None = None,
        source: str | None = None,
        success: bool | None = None,
        execution_backend: str | None = None,
    ) -> tuple[list[ToolExecutionLogContract], int]:
        """List tool execution audit rows for an organization.

        Args:
            organization_id: Organization scope to query.
            limit: Maximum rows to return.
            offset: Row offset for pagination.
            tool_name: Optional tool-name filter.
            source: Optional source filter.
            success: Optional success filter.
            execution_backend: Optional backend filter.

        Returns:
            A tuple of paginated execution logs and total matching rows.
        """
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                query = db.query(ToolExecutionLogModel).filter(ToolExecutionLogModel.organization_id == organization_id)
                if tool_name:
                    query = query.filter(ToolExecutionLogModel.tool_name == tool_name)
                if source:
                    query = query.filter(ToolExecutionLogModel.source == source)
                if success is not None:
                    query = query.filter(ToolExecutionLogModel.success.is_(success))
                if execution_backend:
                    query = query.filter(ToolExecutionLogModel.execution_backend == execution_backend)
                total = query.count()
                rows = query.order_by(ToolExecutionLogModel.created_at.desc()).offset(offset).limit(limit).all()
                return [ToolExecutionLogContract.model_validate(row) for row in rows], total
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(f"Unable to list tool execution logs: {exc}") from exc

    def get_execution_log(self, execution_id: str, organization_id: str) -> ToolExecutionLogContract | None:
        """Fetch one tool execution audit row by identifier.

        Args:
            execution_id: Unique execution-log identifier.
            organization_id: Organization scope to query.

        Returns:
            The matching execution log contract, or `None` when no row exists.
        """
        try:
            with self.current_db.get_custom_db_contxt_session(self.current_db_engine) as db:
                row = db.query(ToolExecutionLogModel).filter(
                    ToolExecutionLogModel.id == execution_id,
                    ToolExecutionLogModel.organization_id == organization_id,
                ).first()
                return ToolExecutionLogContract.model_validate(row) if row else None
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(f"Unable to fetch tool execution log {execution_id}: {exc}") from exc

    # endregion Execution Log Persistence
