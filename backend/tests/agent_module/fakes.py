from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, event
from sqlalchemy.orm import scoped_session, sessionmaker

from agent.db_models import (
    AgentDefinitionModel,
    AgentMessageModel,
    AgentRunModel,
    AgentSessionModel,
    AgentTraceEventModel,
    AgentTraceRunModel,
)
from agent.models.interface import (
    AgentDefinitionContract,
    AgentMessageContract,
    AgentRunContract,
    AgentSessionContract,
    AgentTraceEventContract,
    AgentTraceRunContract,
    AgentTraceSessionContract,
)
from entities.models.response import EntityTypeRecordResponse
from tools.models.interface import ToolExecutionLogContract


class StubLlmManager:
    def __init__(self, *, model: str = "fake-model", api_key: str | None = None) -> None:
        self.model = model
        self.api_key = api_key

    def resolve_model_for_feature(self, organization_id: str, feature: str) -> str:
        assert organization_id
        assert feature == "playbook_agent"
        return self.model

    def resolve_api_key_for_model(self, organization_id: str | None, model: str) -> str | None:
        assert organization_id
        assert model == self.model
        return self.api_key

    def build_agent_chat_model(
        self, *, organization_id: str | None, model_name: str, **kwargs
    ):
        self.agent_chat_model_calls = getattr(self, "agent_chat_model_calls", [])
        self.agent_chat_model_calls.append(
            {"organization_id": organization_id, "model_name": model_name, "kwargs": kwargs}
        )
        if self.api_key is None:
            from exceptions import ServiceError

            raise ServiceError(
                "No OpenAI API key is configured for this organization. "
                "Add one under Settings -> Integrations."
            )

        class _Model:
            captured_llm_requests: list[dict[str, object]] = []

        return _Model()

class StubEntitiesManager:
    def list_entity_type_records(self, *, organization_id: str) -> list[EntityTypeRecordResponse]:
        return [
            EntityTypeRecordResponse(
                entity_type_id="et-application",
                organization_id=organization_id,
                name="application",
                schema_definition={"fields": []},
                version=1,
                is_active=True,
            )
        ]


class InMemoryToolsModelServiceFake:
    def __init__(self) -> None:
        self.execution_logs: dict[str, dict[str, object]] = {}

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _execution_log(record: dict[str, object]) -> ToolExecutionLogContract:
        return ToolExecutionLogContract.model_validate(record)

    def create_execution_log(self, payload: dict[str, object]) -> ToolExecutionLogContract:
        record = {
            "id": str(payload.get("id") or uuid4()),
            "organization_id": str(payload["organization_id"]),
            "user_id": payload.get("user_id"),
            "actor_id": payload.get("actor_id"),
            "actor_type": payload.get("actor_type"),
            "source": str(payload.get("source") or "tools"),
            "tool_name": str(payload["tool_name"]),
            "arguments": dict(payload.get("arguments") or {}),
            "result": dict(payload.get("result") or {}),
            "success": bool(payload.get("success", False)),
            "error": payload.get("error"),
            "duration_ms": int(payload.get("duration_ms") or 0),
            "execution_backend": str(payload.get("execution_backend") or "unknown"),
            "run_id": payload.get("run_id"),
            "session_id": payload.get("session_id"),
            "entity_id": payload.get("entity_id"),
            "entity_type": payload.get("entity_type"),
            "request_id": payload.get("request_id"),
            "metadata_json": dict(payload.get("metadata") or {}),
            "created_at": payload.get("created_at") or self._now(),
        }
        self.execution_logs[str(record["id"])] = record
        return self._execution_log(record)

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
        rows = []
        for record in self.execution_logs.values():
            if record["organization_id"] != organization_id:
                continue
            if tool_name and record["tool_name"] != tool_name:
                continue
            if source and record["source"] != source:
                continue
            if success is not None and record["success"] is not success:
                continue
            if execution_backend and record["execution_backend"] != execution_backend:
                continue
            rows.append(self._execution_log(record))
        rows.sort(key=lambda item: item.created_at, reverse=True)
        total = len(rows)
        return rows[offset : offset + limit], total

    def get_execution_log(
        self, execution_id: str, organization_id: str
    ) -> ToolExecutionLogContract | None:
        record = self.execution_logs.get(execution_id)
        if not record or record["organization_id"] != organization_id:
            return None
        return self._execution_log(record)


class InMemoryAgentModelServiceFake:
    def __init__(self) -> None:
        self.definitions: dict[str, dict[str, object]] = {}
        self.sessions: dict[str, dict[str, object]] = {}
        self.messages: dict[str, dict[str, object]] = {}
        self.runs: dict[str, dict[str, object]] = {}
        self.trace_runs: dict[str, dict[str, object]] = {}
        self.trace_events: dict[str, dict[str, object]] = {}

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _definition(record: dict[str, object]) -> AgentDefinitionContract:
        return AgentDefinitionContract.model_validate(record)

    @staticmethod
    def _session(record: dict[str, object]) -> AgentSessionContract:
        return AgentSessionContract.model_validate(record)

    @staticmethod
    def _message(record: dict[str, object]) -> AgentMessageContract:
        return AgentMessageContract.model_validate(record)

    @staticmethod
    def _run(record: dict[str, object]) -> AgentRunContract:
        return AgentRunContract.model_validate(record)

    @staticmethod
    def _trace_run(record: dict[str, object]) -> AgentTraceRunContract:
        return AgentTraceRunContract.model_validate(record)

    @staticmethod
    def _trace_event(record: dict[str, object]) -> AgentTraceEventContract:
        return AgentTraceEventContract.model_validate(record)

    def list_definitions(self, organization_id: str, active_only: bool = True) -> list[AgentDefinitionContract]:
        rows = []
        for record in self.definitions.values():
            if record["organization_id"] != organization_id:
                continue
            if active_only and not record["is_active"]:
                continue
            rows.append(self._definition(record))
        rows.sort(key=lambda item: item.display_name.lower())
        return rows

    def get_definition(self, definition_id: str, organization_id: str) -> AgentDefinitionContract | None:
        record = self.definitions.get(definition_id)
        if not record or record["organization_id"] != organization_id:
            return None
        return self._definition(record)

    def get_definition_by_name(self, organization_id: str, name: str, active_only: bool = True) -> AgentDefinitionContract | None:
        for record in self.definitions.values():
            if record["organization_id"] != organization_id or record["name"] != name:
                continue
            if active_only and not record["is_active"]:
                continue
            return self._definition(record)
        return None

    def create_definition(self, organization_id: str, payload: dict[str, object]) -> AgentDefinitionContract:
        now = self._now()
        created_at = payload.get("created_at") or now
        updated_at = payload.get("updated_at") or created_at
        record = {
            "definition_id": str(payload.get("definition_id") or uuid4()),
            "name": str(payload["name"]),
            "display_name": str(payload["display_name"]),
            "description": payload.get("description"),
            "system_prompt": str(payload["system_prompt"]),
            "allowed_tools": list(payload["allowed_tools"]) if payload.get("allowed_tools") is not None else None,
            "constraints": dict(payload.get("constraints") or {}),
            "suggestions": list(payload.get("suggestions") or []),
            "model_override": payload.get("model_override"),
            "is_active": bool(payload.get("is_active", True)),
            "is_system": bool(payload.get("is_system", False)),
            "organization_id": organization_id,
            "created_at": created_at,
            "updated_at": updated_at,
        }
        self.definitions[str(record["definition_id"])] = record
        return self._definition(record)

    def update_definition(self, definition_id: str, organization_id: str, updates: dict[str, object]) -> AgentDefinitionContract | None:
        record = self.definitions.get(definition_id)
        if not record or record["organization_id"] != organization_id:
            return None
        for key, value in updates.items():
            if key == "constraints" and value is not None:
                record[key] = dict(value)
            elif key in {"suggestions", "allowed_tools"}:
                record[key] = list(value) if value is not None else None
            else:
                record[key] = value
        record["updated_at"] = self._now()
        return self._definition(record)

    def delete_definition(self, definition_id: str, organization_id: str) -> bool:
        record = self.definitions.get(definition_id)
        if not record or record["organization_id"] != organization_id:
            return False
        del self.definitions[definition_id]
        return True

    def create_session(self, definition_id: str | None, user_id: str, organization_id: str, context: dict | None) -> AgentSessionContract:
        now = self._now()
        record = {
            "session_id": str(uuid4()),
            "definition_id": definition_id,
            "user_id": user_id,
            "organization_id": organization_id,
            "context": dict(context) if context is not None else None,
            "title": None,
            "total_tokens": 0,
            "message_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        self.sessions[str(record["session_id"])] = record
        return self._session(record)

    def get_session(self, session_id: str, user_id: str | None = None, organization_id: str | None = None) -> AgentSessionContract | None:
        record = self.sessions.get(session_id)
        if not record:
            return None
        if user_id and record["user_id"] != user_id:
            return None
        if organization_id and record["organization_id"] != organization_id:
            return None
        return self._session(record)

    def list_sessions(
        self, user_id: str, organization_id: str, limit: int, offset: int
    ) -> list[AgentSessionContract]:
        rows = [
            self._session(record)
            for record in self.sessions.values()
            if record["user_id"] == user_id and record["organization_id"] == organization_id
        ]
        rows.sort(key=lambda item: item.updated_at, reverse=True)
        return rows[offset : offset + limit]

    def update_session(
        self,
        session_id: str,
        *,
        context: dict | None = None,
        title: str | None = None,
        token_delta: int = 0,
        message_delta: int = 0,
    ) -> AgentSessionContract | None:
        record = self.sessions.get(session_id)
        if not record:
            return None
        if context is not None:
            record["context"] = dict(context)
        if title is not None:
            record["title"] = title
        record["total_tokens"] = int(record["total_tokens"]) + token_delta
        record["message_count"] = int(record["message_count"]) + message_delta
        record["updated_at"] = self._now()
        return self._session(record)

    def delete_session(self, session_id: str, user_id: str, organization_id: str) -> bool:
        record = self.sessions.get(session_id)
        if (
            not record
            or record["user_id"] != user_id
            or record["organization_id"] != organization_id
        ):
            return False
        self.sessions.pop(session_id, None)
        for message_id in [key for key, value in self.messages.items() if value["session_id"] == session_id]:
            self.messages.pop(message_id, None)
        return True

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
        record = {
            "message_id": str(uuid4()),
            "session_id": session_id,
            "role": role,
            "content": content,
            "tool_calls": list(tool_calls) if tool_calls is not None else None,
            "pending_actions": list(pending_actions) if pending_actions is not None else None,
            "tokens_used": tokens_used,
            "created_at": self._now(),
        }
        self.messages[str(record["message_id"])] = record
        return self._message(record)

    def get_message(self, message_id: str) -> AgentMessageContract | None:
        record = self.messages.get(message_id)
        return self._message(record) if record else None

    def list_messages(self, session_id: str) -> list[AgentMessageContract]:
        rows = [self._message(record) for record in self.messages.values() if record["session_id"] == session_id]
        rows.sort(key=lambda item: item.created_at)
        return rows

    def update_pending_action(self, message_id: str, action_id: str, updates: dict[str, object]) -> AgentMessageContract | None:
        record = self.messages.get(message_id)
        if not record or not record.get("pending_actions"):
            return None
        actions = list(record["pending_actions"])
        for index, action in enumerate(actions):
            if action.get("action_id") != action_id:
                continue
            merged = dict(action)
            merged.update(updates)
            actions[index] = merged
            record["pending_actions"] = actions
            return self._message(record)
        return None

    def create_run(self, payload: dict[str, object]) -> AgentRunContract:
        now = self._now()
        record = {
            "run_id": str(payload.get("run_id") or uuid4()),
            "organization_id": str(payload["organization_id"]),
            "definition_id": str(payload["definition_id"]),
            "session_id": payload.get("session_id"),
            "user_id": payload.get("user_id"),
            "status": str(payload.get("status") or "queued"),
            "input_text": str(payload["input_text"]),
            "output_text": payload.get("output_text"),
            "error": payload.get("error"),
            "backend_metadata": dict(payload.get("backend_metadata") or {}),
            "execution_context": dict(payload.get("execution_context") or {}),
            "started_at": payload.get("started_at"),
            "completed_at": payload.get("completed_at"),
            "created_at": payload.get("created_at") or now,
            "updated_at": payload.get("updated_at") or now,
        }
        self.runs[str(record["run_id"])] = record
        return self._run(record)

    def update_run(
        self, run_id: str, organization_id: str, updates: dict[str, object]
    ) -> AgentRunContract | None:
        record = self.runs.get(run_id)
        if not record or record["organization_id"] != organization_id:
            return None
        for key, value in updates.items():
            if key in {"backend_metadata", "execution_context"} and value is not None:
                record[key] = dict(value)
            else:
                record[key] = value
        record["updated_at"] = self._now()
        return self._run(record)

    def get_run(self, run_id: str, organization_id: str) -> AgentRunContract | None:
        record = self.runs.get(run_id)
        if not record or record["organization_id"] != organization_id:
            return None
        return self._run(record)

    def list_runs(
        self,
        organization_id: str,
        *,
        limit: int,
        offset: int,
        status: str | None = None,
        definition_id: str | None = None,
    ) -> tuple[list[AgentRunContract], int]:
        rows = []
        for record in self.runs.values():
            if record["organization_id"] != organization_id:
                continue
            if status and record["status"] != status:
                continue
            if definition_id and record["definition_id"] != definition_id:
                continue
            rows.append(self._run(record))
        rows.sort(key=lambda item: item.created_at, reverse=True)
        total = len(rows)
        return rows[offset : offset + limit], total

    def persist_trace(self, run_data: dict, events: list[dict]) -> AgentTraceRunContract:
        now = self._now()
        run_payload = dict(run_data)
        run_payload.setdefault("id", str(uuid4()))
        run_payload.setdefault("created_at", now)
        run_payload.setdefault("updated_at", now)
        self.trace_runs[str(run_payload["id"])] = run_payload
        for event in events:
            event_payload = {
                "id": str(uuid4()),
                "run_id": run_payload["id"],
                "seq": int(event.get("seq", 0)),
                "kind": str(event.get("kind", "event")),
                "payload": dict(event.get("payload") or {}),
                "created_at": now,
            }
            self.trace_events[str(event_payload["id"])] = event_payload
        self.delete_expired_traces(now)
        return self._trace_run(run_payload)

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
        rows = []
        now = self._now()
        for record in self.trace_runs.values():
            if record["organization_id"] != organization_id:
                continue
            expires_at = record.get("expires_at")
            if expires_at and expires_at <= now:
                continue
            if status and record.get("status") != status:
                continue
            if agent_name and record.get("agent_name") != agent_name:
                continue
            if run_type and record.get("run_type") != run_type:
                continue
            if session_id and record.get("session_id") != session_id:
                continue
            rows.append(self._trace_run(record))
        rows.sort(key=lambda item: item.started_at, reverse=True)
        total = len(rows)
        return rows[offset : offset + limit], total

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
        runs = []
        now = self._now()
        for record in self.trace_runs.values():
            if record["organization_id"] != organization_id:
                continue
            expires_at = record.get("expires_at")
            if expires_at and expires_at <= now:
                continue
            if status and record.get("status") != status:
                continue
            if agent_name and record.get("agent_name") != agent_name:
                continue
            if run_type and record.get("run_type") != run_type:
                continue
            runs.append(self._trace_run(record))
        grouped: dict[str, list[AgentTraceRunContract]] = {}
        for run in runs:
            session_key = run.session_id or f"run:{run.id}"
            grouped.setdefault(session_key, []).append(run)

        sessions: list[AgentTraceSessionContract] = []
        for session_key, session_runs in grouped.items():
            ordered = sorted(session_runs, key=lambda item: item.started_at)
            latest = max(session_runs, key=lambda item: item.started_at)
            sessions.append(
                AgentTraceSessionContract(
                    session_id=session_key,
                    organization_id=organization_id,
                    user_id=latest.user_id,
                    agent_name=latest.agent_name,
                    latest_run_id=latest.id,
                    latest_message_id=latest.message_id,
                    latest_status=latest.status,
                    latest_input_message=latest.input_message,
                    model=latest.model,
                    run_count=len(session_runs),
                    total_tokens=sum(int(item.tokens_used or 0) for item in session_runs),
                    total_duration_ms=sum(int(item.duration_ms or 0) for item in session_runs),
                    first_started_at=ordered[0].started_at,
                    last_started_at=latest.started_at,
                    last_completed_at=latest.completed_at,
                )
            )
        sessions.sort(key=lambda item: item.last_started_at, reverse=True)
        total = len(sessions)
        return sessions[offset : offset + limit], total

    def get_trace_run(self, run_id: str, organization_id: str) -> AgentTraceRunContract | None:
        record = self.trace_runs.get(run_id)
        if not record or record["organization_id"] != organization_id:
            return None
        expires_at = record.get("expires_at")
        if expires_at and expires_at <= self._now():
            return None
        return self._trace_run(record)

    def list_trace_events(self, run_id: str) -> list[AgentTraceEventContract]:
        rows = [self._trace_event(record) for record in self.trace_events.values() if record["run_id"] == run_id]
        rows.sort(key=lambda item: item.seq)
        return rows

    def delete_expired_traces(self, cutoff: datetime) -> None:
        expired_runs = [run_id for run_id, record in self.trace_runs.items() if record.get("expires_at") and record["expires_at"] <= cutoff]
        for run_id in expired_runs:
            self.trace_runs.pop(run_id, None)
            for event_id in [key for key, value in self.trace_events.items() if value["run_id"] == run_id]:
                self.trace_events.pop(event_id, None)


class SQLitePostgresDBServiceFake:
    def __init__(self, database_path: Path) -> None:
        self.engine = create_engine(
            f"sqlite:///{database_path}",
            connect_args={"check_same_thread": False},
        )
        self._enable_sqlite_foreign_keys()
        AgentDefinitionModel.metadata.create_all(
            self.engine,
            tables=[
                AgentDefinitionModel.__table__,
                AgentSessionModel.__table__,
                AgentMessageModel.__table__,
                AgentRunModel.__table__,
                AgentTraceRunModel.__table__,
                AgentTraceEventModel.__table__,
            ],
        )

    def _enable_sqlite_foreign_keys(self) -> None:
        @event.listens_for(self.engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    @contextmanager
    def get_custom_db_contxt_session(self, engine):  # noqa: ANN001
        connection = None
        db_session = None
        try:
            connection = engine.connect()
            db_session = scoped_session(sessionmaker(autocommit=False, autoflush=True, bind=engine, expire_on_commit=False))
            yield db_session
        except Exception:
            if db_session:
                db_session.rollback()
            raise
        finally:
            if db_session:
                db_session.close()
            if connection:
                connection.close()

    def dispose(self) -> None:
        AgentDefinitionModel.metadata.drop_all(
            self.engine,
            tables=[
                AgentTraceEventModel.__table__,
                AgentTraceRunModel.__table__,
                AgentRunModel.__table__,
                AgentMessageModel.__table__,
                AgentSessionModel.__table__,
                AgentDefinitionModel.__table__,
            ],
        )
        self.engine.dispose()


class DatabaseServiceManagerFake:
    def __init__(self, db_service: SQLitePostgresDBServiceFake) -> None:
        self._db_service = db_service

    def postgres_db_service(self) -> SQLitePostgresDBServiceFake:
        return self._db_service
