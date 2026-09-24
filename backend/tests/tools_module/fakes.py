from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

from sqlalchemy import create_engine, event
from sqlalchemy.orm import scoped_session, sessionmaker

from entities.models.interface import FieldDefinition, FormConfigContract
from entities.models.response import EntityRecordListResponse
from communications.models.response import CommentCreateResponse
from entities.models.response import EntityRecordResponse, EntityTypeRecordResponse
from exceptions import NotFoundError, ValidationError
from integrations.models.response import CalendarEventResponse, CalendarEventsListResponse
from tools.db_models import ToolExecutionLogModel
from workflow.models.interface import (
    AvailableTransition,
    EntityState,
    StateMachineRecord,
)
from workflow.models.response import (
    AvailableTransitionsResponse,
    TransitionExecutionResponse,
    WorkflowEnrollmentSummary,
    WorkflowEnrollmentSummaryPage,
    WorkflowListResponse,
)

if TYPE_CHECKING:
    from connectors.models.interface import ConnectorContract


class StubEntitiesManager:
    """Stateful entity stub that mirrors the actor-facing manager invariants.

    The entity CRUD tools must call the ``*_for_actor`` methods so they inherit
    unique-identifier validation (create) and field merging (update). This stub
    implements those semantics and treats any call to the system-level methods
    as a test failure, so a regression back to the bypassing path is caught.
    """

    IDENTIFIER_FIELD = "external_id"

    def __init__(self) -> None:
        self.records: dict[str, EntityRecordResponse] = {}
        self.create_for_actor_called = False
        self.update_for_actor_called = False
        self.archive_for_actor_called = False
        self.last_actor: dict[str, object] | None = None

    def list_entity_type_records(self, *, organization_id: str) -> list[EntityTypeRecordResponse]:
        """Return a fixed entity-type list for the supplied organization."""
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

    def get_entity_type_record(
        self, *, organization_id: str, name: str
    ) -> EntityTypeRecordResponse | None:
        if name != "ATS.Candidate":
            return None
        return EntityTypeRecordResponse(
            entity_type_id="et-candidate",
            organization_id=organization_id,
            name=name,
            schema_definition={"identifier_label": "Candidate Unique Name"},
            version=1,
            is_active=True,
        )

    def seed_record(self, record: EntityRecordResponse) -> None:
        """Preload a record so update/delete handlers have something to act on."""
        self.records[record.entity_id] = record

    # region Actor-facing methods (the ones the tools must use)
    def create_entity_record_for_actor(  # noqa: ANN001
        self, actor, request, *, require_reference_sources: bool = True
    ) -> EntityRecordResponse:
        """Create after a unique-identifier check, mirroring the real manager."""
        self.create_for_actor_called = True
        self.last_actor = actor
        self.last_create_request = request
        self.last_require_reference_sources = require_reference_sources
        identifier = (request.data or {}).get(self.IDENTIFIER_FIELD)
        if identifier is not None and any(
            (rec.data or {}).get(self.IDENTIFIER_FIELD) == identifier for rec in self.records.values()
        ):
            raise ValidationError(f"identifier '{identifier}' already exists")
        record = EntityRecordResponse(
            entity_id=f"entity-{len(self.records) + 1}",
            organization_id=str(request.organization_id),
            entity_type_id=request.entity_type_id,
            data=dict(request.data or {}),
            owner_id=request.owner_id,
        )
        self.records[record.entity_id] = record
        return record

    def update_entity_record_for_actor(
        self, actor, entity_id, request, organization_id=None
    ) -> EntityRecordResponse:  # noqa: ANN001
        """Merge the partial update into the existing record's data."""
        self.update_for_actor_called = True
        self.last_actor = actor
        existing = self.records.get(entity_id)
        if existing is None:
            raise NotFoundError(f"entity not found: {entity_id}")
        merged = {**(existing.data or {}), **(request.data or {})}
        updated = existing.model_copy(
            update={"data": merged, "owner_id": request.owner_id or existing.owner_id}
        )
        self.records[entity_id] = updated
        return updated

    def archive_entity_record_for_actor(
        self, actor, entity_id, organization_id=None
    ) -> EntityRecordResponse:  # noqa: ANN001
        """Soft-archive an existing record."""
        self.archive_for_actor_called = True
        self.last_actor = actor
        existing = self.records.get(entity_id)
        if existing is None:
            raise NotFoundError(f"entity not found: {entity_id}")
        return existing.model_copy(
            update={"archived_at": datetime(2026, 3, 13, tzinfo=timezone.utc)}
        )

    # endregion

    # region System-level methods (must NOT be called by the tools)
    def get_entity_record_for_actor(self, actor, entity_id, organization_id=None):  # noqa: ANN001, ANN201
        """Actor-scoped fetch; raises when absent, mirroring the real manager."""
        record = self.records.get(entity_id)
        if record is None:
            raise NotFoundError(f"entity record '{entity_id}' not found")
        return record

    def list_entity_records_for_actor(  # noqa: ANN201
        self, actor, organization_id=None, entity_type_id=None, include_archived=False  # noqa: ANN001
    ):
        """Actor-scoped listing filtered by entity type, like the real manager.

        Returns the real response model: a loose stand-in here once let a wrong
        field name ('records' instead of 'items') pass tests and fail in the app.
        """
        records = [
            record
            for record in self.records.values()
            if entity_type_id is None or record.entity_type_id == entity_type_id
        ]
        return EntityRecordListResponse(organization_id=organization_id or "org-1", items=records)

    def create_entity_record(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        raise AssertionError("create_entity tool must call create_entity_record_for_actor")

    def update_entity_record(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        raise AssertionError("update_entity tool must call update_entity_record_for_actor")

    def archive_entity_record(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        raise AssertionError("delete_entity tool must call archive_entity_record_for_actor")

    # endregion

    def get_form_config_definition(self, organization_id: str, form_key: str) -> FormConfigContract | None:
        if form_key != "ATS.Candidate":
            return None
        return FormConfigContract.model_construct(
            organization_id=organization_id,
            form_key=form_key,
            fields=[
                FieldDefinition.model_construct(name="full_name", field_type="text", required=True, options=()),
                FieldDefinition.model_construct(
                    name="candidate_source",
                    field_type="select",
                    required=False,
                    options=("Referral", "Website"),
                ),
            ],
            version=2,
        )

    def list_form_config_definitions(self, organization_id: str) -> list[FormConfigContract]:
        form_config = self.get_form_config_definition(organization_id, "ATS.Candidate")
        return [form_config] if form_config is not None else []

    def get_form_fields(self, organization_id: str, form_key: str) -> list[dict]:
        """Raw merged field dicts (as forms.active_schema_fields returns), including a
        Table/Grid field, so get_form_schema's table handling can be asserted."""
        _ = organization_id
        if form_key != "ATS.Candidate":
            return []
        return [
            {"field": "full_name", "type": "text", "required": True, "enum_values": []},
            {"field": "candidate_source", "type": "select", "required": False,
             "enum_values": ["Referral", "Website"]},
            {
                "field": "skills_table",
                "type": "json",
                "required": False,
                "enum_values": [],
                "table_config": {
                    "row_mode": "dynamic",
                    "min_rows": 0,
                    "max_rows": None,
                    "columns": [
                        {"id": "skill", "label": "Skill", "type": "text", "required": True},
                        {"id": "years", "label": "Years", "type": "number"},
                        {"id": "score", "label": "Score", "type": "number", "calc": {"op": "sum"}},
                    ],
                },
            },
        ]


class StubDocumentsManager:
    """Provide predictable document-source behavior for tools tests."""

    def read_document_source(
        self,
        organization_id: str,
        *,
        document_id: str | None = None,
        storage_key: str | None = None,
    ) -> dict[str, object] | None:
        _ = organization_id
        if document_id not in {None, "doc-1"} and storage_key not in {None, "documents/resume.txt"}:
            return None

        return {
            "document_id": document_id or "doc-1",
            "storage_key": storage_key or "documents/resume.txt",
            "filename": "resume.txt",
            "content_type": "text/plain",
            "file_bytes": b"Hello world",
            "status": "uploaded",
            "metadata": {"storage_key": storage_key or "documents/resume.txt"},
        }


class StubFileprocessorManager:
    """Parse file bytes for tools tests, mirroring extract_content's contract."""

    def extract_content(
        self,
        *,
        filename: str,
        content_type: str,
        file_bytes: bytes,
        max_text_chars: int | None = None,
    ) -> dict[str, object]:
        _ = max_text_chars
        if not file_bytes:
            return {
                "filename": filename,
                "content_type": content_type,
                "detected_format": "unknown",
                "text": "",
                "images": [],
                "tables": [],
                "parse_ok": False,
                "parse_error": "file_bytes is empty",
                "truncated": False,
            }
        return {
            "filename": filename,
            "content_type": content_type,
            "detected_format": "text",
            "text": file_bytes.decode("utf-8", errors="replace"),
            "images": [],
            "tables": [],
            "parse_ok": True,
            "parse_error": None,
            "truncated": False,
        }


class StubCommunicationsManager:
    """Provide predictable comment-creation behavior for tools tests."""

    def __init__(self) -> None:
        """Initialize the stub communications manager.

        Args:
            None.

        Returns:
            `None`.
        """
        self.last_payload: dict[str, object] | None = None

    def create_comment(self, request) -> CommentCreateResponse:  # noqa: ANN001
        """Store and return one created comment payload.

        Args:
            request: Comment creation request received from the tools manager.

        Returns:
            A deterministic comment-create response.
        """
        self.last_payload = request.model_dump()
        return CommentCreateResponse(
            comment_id="comment-1",
            entity_id=request.entity_id,
            organization_id=request.organization_id,
            author_id=request.author_id,
            body=request.body,
            mentions=list(request.mentions),
            mention_count=len(request.mentions),
            created_at="2026-03-13T00:00:00Z",
        )


class StubCommentsManager:
    """Mirror CommentsServiceManager's real agent-facing signatures."""

    def __init__(self) -> None:
        self.last_call: dict[str, object] | None = None
        self.comments: list[object] = []

    def create_comment_for_agent(self, actor, entity_id, request):  # noqa: ANN001, ANN201
        self.last_call = {"entity_id": entity_id, "actor": actor, "text": request.text}
        return SimpleNamespace(
            id="comment-1",
            model_dump=lambda: {"id": "comment-1", "text": request.text},
        )

    def list_comments_for_agent(self, actor, entity_id, **kwargs):  # noqa: ANN001, ANN201
        self.last_call = {"entity_id": entity_id, "actor": actor, "kwargs": kwargs}
        return SimpleNamespace(comments=list(self.comments), total=len(self.comments))


class StubIntegrationsManager:
    """Provide predictable calendar scheduling behavior for tools tests."""

    def __init__(self) -> None:
        """Initialize the stub integration manager.

        Args:
            None.

        Returns:
            `None`.
        """
        self.last_payload: dict[str, object] | None = None

    def schedule_event(self, payload: dict[str, object]) -> CalendarEventResponse:
        """Store and return one scheduled-event payload.

        Args:
            payload: Calendar scheduling payload.

        Returns:
            A deterministic calendar event response.
        """
        self.last_payload = dict(payload)
        return CalendarEventResponse(
            event_id="evt-1",
            organization_id=str(payload["organization_id"]),
            user_id=str(payload["user_id"]),
            provider=str(payload["provider"]),
            title=str(payload["title"]),
            starts_at=str(payload["starts_at"]),
            ends_at=str(payload["ends_at"]),
            attendees=list(payload.get("attendees") or []),
            entity_id=payload.get("entity_id"),
        )

    def list_events(self, payload: dict[str, object]) -> CalendarEventsListResponse:
        organization_id = str(payload["organization_id"])
        user_id = str(payload.get("user_id") or "recruiter-user")
        provider = str(payload.get("provider") or "google")
        return CalendarEventsListResponse(
            items=[
                CalendarEventResponse(
                    event_id="evt-1",
                    organization_id=organization_id,
                    user_id=user_id,
                    provider=provider,
                    title="Interview",
                    starts_at="2026-03-20T10:00:00Z",
                    ends_at="2026-03-20T11:00:00Z",
                    attendees=["candidate@example.com"],
                    entity_id="entity-1",
                ),
                CalendarEventResponse(
                    event_id="evt-2",
                    organization_id=organization_id,
                    user_id=user_id,
                    provider=provider,
                    title="Internal Sync",
                    starts_at="2026-03-21T10:00:00Z",
                    ends_at="2026-03-21T11:00:00Z",
                    attendees=["team@example.com"],
                    entity_id="entity-2",
                ),
            ]
        )


class StubWorkflowManager:
    """Provide predictable workflow enrollment behavior for tools tests."""

    def __init__(self) -> None:
        """Initialize captured enrollment state."""
        self.last_actor: dict[str, object] | None = None
        self.last_machine_name: str | None = None
        self.last_entity_id: str | None = None
        self.last_current_state: str | None = None

    def enroll_entity_for_actor(self, actor, machine_name: str, entity_id: str) -> EntityState:  # noqa: ANN001
        """Capture and return one deterministic enrollment response."""
        self.last_actor = actor
        self.last_machine_name = machine_name
        self.last_entity_id = entity_id
        return EntityState(
            entity_id=entity_id,
            entity_type="Candidate",
            organization_id=str(actor["organization_id"]),
            machine_name=machine_name,
            machine_version=2,
            workflow_id="workflow-1",
            current_state="INITIAL",
            state_version=0,
            data={"name": "Dhiraj Nambiar"},
        )

    @staticmethod
    def _stub_state_machine_record(actor, machine_name: str) -> StateMachineRecord:  # noqa: ANN001
        return StateMachineRecord.model_construct(
            id="workflow-row-1",
            machine_key="candidate_pipeline",
            machine_name=machine_name,
            name="Candidate Pipeline",
            description=None,
            entity_type="ATS.Candidate",
            version=2,
            is_active=True,
            # Real states, so list_workflows can publish them and the state
            # resolver has something to match against.
            definition=SimpleNamespace(
                states=[SimpleNamespace(name=name) for name in ("INITIAL", "SCREENING", "HIRED")]
            ),
            canvas_metadata=None,
            organization_id=str(actor["organization_id"]),
            created_at=None,
        )

    def get_active_state_machine_for_actor(self, actor, machine_name: str) -> StateMachineRecord:  # noqa: ANN001
        """Return one deterministic active workflow record."""
        self.last_actor = actor
        self.last_machine_name = machine_name
        return self._stub_state_machine_record(actor, machine_name)

    def list_enrollment_summaries_for_actor(
        self,
        actor,  # noqa: ANN001
        *,
        machine_name: str | None = None,
        current_state: str | None = None,
        **_kwargs: object,
    ) -> WorkflowEnrollmentSummaryPage:
        """Return one deterministic enrollment summary for `machine_name`."""
        self.last_actor = actor
        self.last_machine_name = machine_name
        self.last_current_state = current_state
        summary = WorkflowEnrollmentSummary(
            state_id="state-1",
            entity_id="entity-1",
            entity_type_id="entity-type-1",
            entity_type="Candidate",
            organization_id=str(actor["organization_id"]),
            workflow_id="workflow-row-1",
            machine_name=machine_name or "",
            machine_display_name="Test Workflow",
            machine_version=2,
            current_state=current_state or "INITIAL",
            state_version=0,
            display_name="Dhiraj Nambiar",
            owner_id="user-1",
            assignee_id="user-2",
            owner_name="Vinay Kumar",
            assignee_name="Priya Sharma",
        )
        return WorkflowEnrollmentSummaryPage(items=[summary])

    def list_state_machines_scoped_for_actor(
        self, actor, payload, include_archived: bool = False  # noqa: ANN001
    ) -> WorkflowListResponse:
        """Return one deterministic published workflow."""
        _ = include_archived
        self.last_actor = actor
        return WorkflowListResponse(
            scope=str(payload.scope),
            published_items=[self._stub_state_machine_record(actor, "workflow_m4vsvyi9_6c51sk")],
        )

    def list_available_transitions_for_actor(
        self, actor, machine_name, current_state, entity_id, inputs=None  # noqa: ANN001
    ) -> AvailableTransitionsResponse:
        """Deterministic transitions: SCREENING allowed, HIRED blocked."""
        _ = actor, machine_name, current_state, inputs
        return AvailableTransitionsResponse(
            entity_id=entity_id,
            current_state="INITIAL",
            available_transitions=[
                AvailableTransition(trigger="to_screening", to_state="SCREENING", allowed=True),
                AvailableTransition(
                    trigger="to_hired", to_state="HIRED", allowed=False, blocked_reasons=["needs approval"]
                ),
            ],
        )

    def execute_transition_for_actor(  # noqa: ANN001
        self, actor, entity_id, payload, *, _system_initiated: bool = False
    ) -> TransitionExecutionResponse:
        """Capture the trigger and return a deterministic transition result.

        Signature mirrors the real method exactly. It previously accepted a 4th positional
        `db`, which the real method does not, so a caller passing a session positionally
        would have passed here and raised TypeError in production.
        """
        _ = actor, _system_initiated
        self.last_trigger = payload.trigger
        return TransitionExecutionResponse(
            transition_id="t-1",
            event_id="e-1",
            entity_id=entity_id,
            from_state="INITIAL",
            to_state="SCREENING",
            state_version=1,
        )


class StubDashboardServiceManager:
    """Provide predictable metric-query behavior for tools tests.

    Mirrors the real `DashboardServiceManager.db.run_metric(...)` shape by
    exposing itself as its own `.db` — the tool handler only ever calls
    `dashboard_service_manager.db.run_metric(...)`.
    """

    # States this org "has", used to resolve the casing of a requested state.
    STATES = ("INITIAL", "SCREENING", "HIRED")

    def __init__(self) -> None:
        self.last_organization_id: str | None = None
        self.last_metric_key: str | None = None
        self.last_filters: dict[str, object] | None = None
        self.last_filter_options_workflow_id: str | None = None
        # Set to an error payload to mimic a widget the dashboard failed to run.
        self.widget_data: dict[str, object] | None = None
        self.db = self

    def get_filter_options_for_actor(
        self, actor: dict[str, object], workflow_id: str | None = None
    ) -> SimpleNamespace:
        """Mirror the real filter-options response, states only."""
        self.last_actor = actor
        self.last_filter_options_workflow_id = workflow_id
        return SimpleNamespace(
            states=[SimpleNamespace(value=name, label=name) for name in self.STATES]
        )

    def run_metric(
        self,
        organization_id: str,
        metric_key: str,
        filters: dict[str, object] | None = None,
    ) -> dict[str, object]:
        self.last_organization_id = organization_id
        self.last_metric_key = metric_key
        self.last_filters = dict(filters or {})
        return {"value": 42, "prevValue": 30, "trend": [{"label": "Last week", "value": 30}]}

    def get_data_for_actor(
        self,
        actor: dict[str, object],
        items: list[object],
        anchor_entity_id: str | None = None,
    ) -> SimpleNamespace:
        """Return one canned DashboardWidgetData per requested item, keyed by widget_id."""
        _ = anchor_entity_id
        self.last_actor = actor
        self.last_items = list(items)
        payload = self.widget_data or {"kind": "scalar", "value": 42, "prevValue": 30}
        results = {str(item.widget_id): payload for item in items}
        return SimpleNamespace(results=results)

    def get_dashboard_for_actor(self, actor: dict[str, object], key: str) -> SimpleNamespace:
        """Return a deterministic 'primary' dashboard with one metric + one embedded widget."""
        self.last_actor = actor
        self.last_dashboard_key = key
        config = {
            "widgets": [
                {"id": "w-count", "type": "stat", "title": "Total", "metric": "entities.count", "layout": {"x": 0, "y": 0, "w": 12, "h": 4}},
                {"id": "w-board", "type": "embedded", "title": "Board", "componentKey": "pipeline.board", "layout": {"x": 0, "y": 4, "w": 30, "h": 6}},
            ]
        }
        return SimpleNamespace(config=config)


class SQLitePostgresDBServiceFake:
    """Provide a SQLite-backed database service compatible with modular db_models."""

    def __init__(self, database_path: Path) -> None:
        """Create the SQLite engine and materialize tool execution tables.

        Args:
            database_path: SQLite database path used for the test database.

        Returns:
            `None`.
        """
        self.engine = create_engine(
            f"sqlite:///{database_path}",
            connect_args={"check_same_thread": False},
        )
        self._enable_sqlite_foreign_keys()
        ToolExecutionLogModel.metadata.create_all(self.engine, tables=[ToolExecutionLogModel.__table__])

    def _enable_sqlite_foreign_keys(self) -> None:
        """Enable SQLite foreign-key enforcement for the test engine.

        Args:
            None.

        Returns:
            `None`.
        """
        @event.listens_for(self.engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    @contextmanager
    def get_custom_db_contxt_session(self, engine):  # noqa: ANN001
        """Yield one scoped SQLAlchemy session compatible with modular db_models.

        Args:
            engine: SQLAlchemy engine bound to the SQLite database.

        Returns:
            A context-managed scoped session.
        """
        connection = None
        db_session = None
        try:
            connection = engine.connect()
            db_session = scoped_session(
                sessionmaker(autocommit=False, autoflush=True, bind=engine, expire_on_commit=False)
            )
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
        """Drop created tables and dispose the SQLite engine.

        Args:
            None.

        Returns:
            `None`.
        """
        ToolExecutionLogModel.metadata.drop_all(self.engine, tables=[ToolExecutionLogModel.__table__])
        self.engine.dispose()


class DatabaseServiceManagerFake:
    """Provide the modular `postgres_db_service()` interface for tests."""

    def __init__(self, db_service: SQLitePostgresDBServiceFake) -> None:
        """Store the backing SQLite service.

        Args:
            db_service: SQLite-backed database service used by db_models.

        Returns:
            `None`.
        """
        self._db_service = db_service

    def postgres_db_service(self) -> SQLitePostgresDBServiceFake:
        """Return the backing SQLite service.

        Args:
            None.

        Returns:
            The SQLite-backed database service.
        """
        return self._db_service


class StubConnectorsDbModelService:
    """Serve a fixed set of connector contracts, keyed by id.

    Backs a real `ConnectorsServiceManager` in tests, so `run_connector_call`
    (bound onto the class at import time in connectors/manager.py) runs for
    real against these contracts rather than a second, hand-rolled fake.
    """

    def __init__(self, connectors: dict[str, ConnectorContract] | None = None) -> None:
        self.connectors = dict(connectors or {})

    def get_connector(self, connector_id: str, organization_id: str) -> ConnectorContract | None:
        contract = self.connectors.get(connector_id)
        return contract if contract and contract.organization_id == organization_id else None

    def get_decrypted_secrets(self, connector_id: str, organization_id: str) -> dict[str, str]:
        _ = connector_id, organization_id
        return {}

    def list_connectors(
        self, organization_id: str, entity_type: str | None = None
    ) -> list[ConnectorContract]:
        _ = entity_type
        return [c for c in self.connectors.values() if c.organization_id == organization_id]
