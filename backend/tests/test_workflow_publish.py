"""Workflow lifecycle tests for draft and published state machines."""

from __future__ import annotations

import os
import socket
from itertools import count
from urllib.parse import urlparse

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from exceptions import ConflictError, NotFoundError, PersistenceError, ValidationError
from workflow.db_models import WorkflowModelService
from workflow.manager import WorkflowServiceManager
from workflow.services import DefinitionAnalysisService
from workflow_manager_factory import make_workflow_manager
from workflow.models import WorkflowPublishRequest
from workflow.models.interface import (
    DefinitionReport,
    EntityState,
    EntitySchema,
    ReportType,
    State,
    StateMachineDefinition,
    StateMachineRecord,
    Transition,
    WorkflowDraftRecord,
    WorkflowDryRunSummary,
)
from workflow.models.request import (
    StateMachineCreateRequest,
    WorkflowDraftCreateRequest,
    WorkflowDraftSeedRequest,
    WorkflowDraftUpdateRequest,
    WorkflowListScopeRequest,
    WorkflowRowLookupRequest,
)


def test_workflow_publish_request_requires_definition() -> None:
    """Publish request still requires a definition payload."""
    with pytest.raises(PydanticValidationError, match="definition"):
        WorkflowPublishRequest()


def test_state_machine_create_request_allows_distinct_definition_machine_key() -> None:
    """Family id and definition machine_key are no longer forced to be equal."""
    request = StateMachineCreateRequest(
        machine_name="workflow_family_id",
        version=1,
        is_active=False,
        definition=_minimal_definition("frontend_machine_key"),
    )
    assert request.machine_name == "workflow_family_id"
    assert request.definition.machine_key == "frontend_machine_key"


_ORG_ID = "test-org-1"
_TEST_ORG_IDS: tuple[str, ...] = ("test-org-1", "test-org-2")


def _minimal_definition(machine_key: str = "pub_test_machine", *, name: str = "Publish Test Machine") -> StateMachineDefinition:
    """Return a minimal valid StateMachineDefinition for testing."""
    return StateMachineDefinition(
        machine_key=machine_key,
        name=name,
        description="Used by workflow publish tests",
        entity_type="publish_entity",
        entity_schema=EntitySchema(entity_type="publish_entity", fields=[]),
        states=[
            State(name="start", tags=["initial"], order=1),
            State(name="end", tags=["terminal"], order=2),
        ],
        initial_state="start",
        transitions=[
            Transition(
                key="start_to_end",
                trigger="complete",
                label="Complete",
                from_state="start",
                to_state="end",
                required_fields=[],
                guards=[],
                pre_transition_tasks=[],
                post_transition_tasks=[],
                auto_transition=None,
                sla_seconds=None,
                description="Test transition",
            )
        ],
    )


def _definition_dict(machine_key: str = "pub_test_machine", *, name: str = "Publish Test Machine") -> dict:
    """Return a minimal definition as a plain dict."""
    return _minimal_definition(machine_key, name=name).model_dump(mode="json")


def _draft_record(
    *, row_id: str, machine_name: str, machine_key: str, definition: dict, created_by: str | None = None
) -> WorkflowDraftRecord:
    return WorkflowDraftRecord(
        id=row_id,
        machine_key=machine_key,
        machine_name=machine_name,
        name=str(definition.get("name")) if definition.get("name") is not None else None,
        description=str(definition.get("description")) if definition.get("description") is not None else None,
        entity_type=str(definition.get("entity_type")),
        version=0,
        is_active=False,
        definition=definition,
        organization_id=_ORG_ID,
        created_by=created_by,
    )


def _published_record(
    *, row_id: str, machine_name: str, version: int, definition: StateMachineDefinition, created_by: str | None = None
) -> StateMachineRecord:
    return StateMachineRecord(
        id=row_id,
        machine_key=definition.machine_key,
        machine_name=machine_name,
        name=definition.name,
        description=definition.description,
        entity_type=definition.entity_type,
        version=version,
        is_active=True,
        definition=definition,
        organization_id=_ORG_ID,
        created_by=created_by,
    )


class _WorkflowLifecycleFakeDb:
    """Small fake DB that models the workflow-family lifecycle."""

    def __init__(self) -> None:
        self._draft_counter = count(1)
        self._published_counter = count(1)
        self.rows: dict[str, WorkflowDraftRecord | StateMachineRecord] = {}

    def create_state_machine_draft(
        self,
        *,
        organization_id: str,
        machine_key: str,
        machine_name: str,
        definition: dict[str, object],
        canvas_metadata=None,
        created_by: str | None = None,
    ) -> WorkflowDraftRecord:
        row_id = f"draft-{next(self._draft_counter)}"
        record = _draft_record(
            row_id=row_id,
            machine_name=machine_name,
            machine_key=machine_key,
            definition=dict(definition),
            created_by=created_by,
        )
        self.rows[row_id] = record
        return record

    def get_state_machine_by_row_id(self, *, organization_id: str, row_id: str):
        row = self.rows.get(row_id)
        if row is None or row.organization_id != organization_id:
            return None
        return row

    def update_state_machine_draft(
        self,
        *,
        organization_id: str,
        row_id: str,
        definition: dict[str, object],
        canvas_metadata=None,
    ) -> WorkflowDraftRecord | None:
        row = self.get_state_machine_by_row_id(
            organization_id=organization_id,
            row_id=row_id,
        )
        if row is None or row.version != 0:
            return None
        updated = _draft_record(
            row_id=row.id,
            machine_name=row.machine_name,
            machine_key=str(definition.get("machine_key") or row.machine_key),
            definition=dict(definition),
            created_by=row.created_by,
        )
        if canvas_metadata is not None:
            updated.canvas_metadata = canvas_metadata
        self.rows[row_id] = updated
        return updated

    def delete_state_machine_by_row_id(
        self,
        *,
        organization_id: str,
        row_id: str,
    ) -> WorkflowDraftRecord | StateMachineRecord | None:
        row = self.get_state_machine_by_row_id(organization_id=organization_id, row_id=row_id)
        if row is None:
            return None
        del self.rows[row_id]
        return row

    def get_next_version(self, *, organization_id: str, machine_name: str) -> int:
        versions = [
            row.version
            for row in self.rows.values()
            if row.organization_id == organization_id and row.machine_name == machine_name
        ]
        return (max(versions) if versions else 0) + 1

    def list_state_machines(self, *, organization_id: str, machine_name: str | None = None, scope: str = "published", include_archived: bool = False):
        _ = include_archived
        rows = [
            row
            for row in self.rows.values()
            if row.organization_id == organization_id and (machine_name is None or row.machine_name == machine_name)
        ]
        if scope == "draft":
            rows = [row for row in rows if row.version == 0]
        elif scope == "published":
            rows = [row for row in rows if row.version >= 1]
        elif scope != "all":
            raise ValueError(scope)
        return sorted(rows, key=lambda row: (row.machine_name, -row.version, row.id or ""))

    def create_state_machine_published(
        self,
        request: StateMachineCreateRequest,
        *,
        organization_id: str,
        created_by: str | None = None,
        method_pins=None,
    ) -> StateMachineRecord:
        row_id = f"published-{next(self._published_counter)}"
        record = _published_record(
            row_id=row_id,
            machine_name=request.machine_name,
            version=request.version,
            definition=request.definition,
            created_by=created_by,
        )
        self.rows[row_id] = record
        return record

    def get_active_state_machine(self, *, organization_id: str, machine_name: str):
        for row in self.rows.values():
            if (
                row.organization_id == organization_id
                and row.machine_name == machine_name
                and getattr(row, "is_active", False)
            ):
                return row
        return None


def _fake_evaluation(manager: WorkflowServiceManager, machine_name: str, candidate_version: int):
    validation = DefinitionAnalysisService().build_preview_report(
        machine_name, candidate_version, ReportType.VALIDATION, []
    )
    dry_run = DefinitionAnalysisService().build_preview_report(
        machine_name, candidate_version, ReportType.DRY_RUN, []
    )
    return validation, dry_run, WorkflowDryRunSummary(), True


def test_manager_workflow_lifecycle_keeps_one_family_identifier(monkeypatch) -> None:
    """Draft saves and publishes should stay within one backend-owned family id."""
    db = _WorkflowLifecycleFakeDb()
    manager = make_workflow_manager(db)
    actor = {"organization_id": _ORG_ID, "user_id": "u1", "roles": ["admin"]}

    monkeypatch.setattr(manager, "_generate_machine_name", lambda: "workflow_family_1")
    monkeypatch.setattr(
        manager,
        "_evaluate_candidate_definition",
        lambda organization_id, machine_name, definition, candidate_version, persist_validation_report, **_kwargs: _fake_evaluation(
            manager,
            machine_name,
            candidate_version,
        ),
    )

    created = manager.create_workflow_draft_for_actor(
        actor,
        WorkflowDraftCreateRequest(name="Flow ABC", description="first draft"),
    )
    assert created.machine_name == "workflow_family_1"
    assert created.definition["name"] == "Flow ABC"

    draft_v1 = manager.update_workflow_draft_for_actor(
        actor,
        created.id,
        WorkflowDraftUpdateRequest(
            definition=_definition_dict("frontend_key_v1", name="Flow ABC Updated"),
        ),
    )
    assert draft_v1.record.machine_name == "workflow_family_1"
    assert draft_v1.record.definition["machine_key"] == "frontend_key_v1"

    published_v1 = manager.publish_workflow_for_actor(
        actor,
        created.id,
        WorkflowPublishRequest(
            definition=_minimal_definition("frontend_publish_key_v1", name="Flow ABC Published"),
        ),
    )
    assert published_v1.state_machine.machine_name == "workflow_family_1"
    assert published_v1.state_machine.version == 1
    assert published_v1.state_machine.definition.machine_key == "frontend_publish_key_v1"

    draft_v2 = manager.update_workflow_draft_for_actor(
        actor,
        created.id,
        WorkflowDraftUpdateRequest(
            definition=_definition_dict("frontend_key_v2", name="Flow ABC Draft Again"),
        ),
    )
    assert draft_v2.record.machine_name == "workflow_family_1"
    assert draft_v2.record.version == 0

    published_v2 = manager.publish_workflow_for_actor(
        actor,
        created.id,
        WorkflowPublishRequest(
            definition=_minimal_definition("frontend_publish_key_v2", name="Flow ABC Published Again"),
        ),
    )
    assert published_v2.state_machine.machine_name == "workflow_family_1"
    assert published_v2.state_machine.version == 2

    listed = manager.list_state_machines_scoped_for_actor(
        actor,
        WorkflowListScopeRequest(scope="all", machine_name="workflow_family_1"),
    )
    assert [item.version for item in listed.published_items] == [2, 1]
    assert [item.version for item in listed.draft_items] == [0]
    assert all(item.machine_name == "workflow_family_1" for item in listed.published_items)
    assert listed.draft_items[0].machine_name == "workflow_family_1"


def test_create_workflow_draft_stamps_created_by_from_actor() -> None:
    """A newly created draft records the acting user as its owner."""
    db = _WorkflowLifecycleFakeDb()
    manager = make_workflow_manager(db)
    actor = {"organization_id": _ORG_ID, "user_id": "creator-1", "roles": ["admin"]}

    created = manager.create_workflow_draft_for_actor(
        actor,
        WorkflowDraftCreateRequest(name="Owned Flow"),
    )

    assert created.created_by == "creator-1"


def test_publish_carries_forward_draft_creator_not_publisher(monkeypatch) -> None:
    """Publishing preserves the original draft author as owner, even when a
    different user (e.g. an admin) performs the publish."""
    db = _WorkflowLifecycleFakeDb()
    manager = make_workflow_manager(db)

    monkeypatch.setattr(
        manager,
        "_evaluate_candidate_definition",
        lambda organization_id, machine_name, definition, candidate_version, persist_validation_report, **_kwargs: _fake_evaluation(
            manager, machine_name, candidate_version,
        ),
    )

    author = {"organization_id": _ORG_ID, "user_id": "author-1", "roles": ["admin"]}
    publisher = {"organization_id": _ORG_ID, "user_id": "publisher-2", "roles": ["admin"]}

    created = manager.create_workflow_draft_for_actor(
        author, WorkflowDraftCreateRequest(name="Team Flow"),
    )

    published = manager.publish_workflow_for_actor(
        publisher,
        created.id,
        WorkflowPublishRequest(definition=_minimal_definition("team_flow_key")),
    )

    assert published.state_machine.created_by == "author-1"


def test_seed_workflow_draft_carries_forward_published_creator() -> None:
    """Seeding a fresh draft from an existing published workflow keeps the
    family's original owner instead of attributing it to whoever reopens it."""
    db = _WorkflowLifecycleFakeDb()
    manager = make_workflow_manager(db)

    db.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name="seeded_family",
            version=1,
            is_active=True,
            definition=_minimal_definition("seeded_family"),
        ),
        organization_id=_ORG_ID,
        created_by="original-author",
    )

    editor = {"organization_id": _ORG_ID, "user_id": "editor-1", "roles": ["admin"]}
    draft = manager.seed_workflow_draft_for_actor(
        editor, "seeded_family", WorkflowDraftSeedRequest(),
    )

    assert draft.created_by == "original-author"


def test_list_state_machines_scoped_resolves_created_by_name() -> None:
    """The list endpoint enriches each row with the owner's display name."""
    db = _WorkflowLifecycleFakeDb()
    db.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name="named_owner",
            version=1,
            is_active=True,
            definition=_minimal_definition("named_owner"),
        ),
        organization_id=_ORG_ID,
        created_by="user-1",
    )

    class _FakeUserService:
        def get_user_display_info(self, user_id: str):
            return {"user-1": "Alice Example"}.get(user_id), None

    manager = make_workflow_manager(db, user_service_manager=_FakeUserService())
    actor = {"organization_id": _ORG_ID, "user_id": "viewer-1", "roles": ["admin"]}

    listing = manager.list_state_machines_scoped_for_actor(
        actor, WorkflowListScopeRequest(scope="published"),
    )

    assert listing.published_items[0].created_by == "user-1"
    assert listing.published_items[0].created_by_name == "Alice Example"


def test_list_state_machines_scoped_without_user_service_leaves_name_unset() -> None:
    """Without a wired user_service_manager, created_by_name stays None rather
    than raising — the list endpoint must still work in that configuration."""
    db = _WorkflowLifecycleFakeDb()
    db.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name="no_user_service",
            version=1,
            is_active=True,
            definition=_minimal_definition("no_user_service"),
        ),
        organization_id=_ORG_ID,
        created_by="user-1",
    )

    manager = make_workflow_manager(db)
    actor = {"organization_id": _ORG_ID, "user_id": "viewer-1", "roles": ["admin"]}

    listing = manager.list_state_machines_scoped_for_actor(
        actor, WorkflowListScopeRequest(scope="published"),
    )

    assert listing.published_items[0].created_by == "user-1"
    assert listing.published_items[0].created_by_name is None


def test_publish_requires_real_draft_row_without_db(monkeypatch) -> None:
    """Publish should fail instead of inferring family id from request payload."""
    db = _WorkflowLifecycleFakeDb()
    manager = make_workflow_manager(db)
    actor = {"organization_id": _ORG_ID, "user_id": "u1", "roles": ["admin"]}

    monkeypatch.setattr(
        manager,
        "_evaluate_candidate_definition",
        lambda organization_id, machine_name, definition, candidate_version, persist_validation_report, **_kwargs: _fake_evaluation(
            manager,
            machine_name,
            candidate_version,
        ),
    )

    with pytest.raises(NotFoundError, match="workflow draft with row_id 'missing-draft' was not found"):
        manager.publish_workflow_for_actor(
            actor,
            "missing-draft",
            WorkflowPublishRequest(definition=_minimal_definition("frontend_machine_key")),
        )


def test_workflow_lists_and_direct_reads_honor_role_scope() -> None:
    db = _WorkflowLifecycleFakeDb()
    allowed = db.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name="allowed",
            version=1,
            is_active=True,
            definition=_minimal_definition("allowed"),
        ),
        organization_id=_ORG_ID,
    )
    hidden = db.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name="hidden",
            version=1,
            is_active=True,
            definition=_minimal_definition("hidden"),
        ),
        organization_id=_ORG_ID,
    )

    class _Roles:
        @staticmethod
        def get_workflow_access_scope(_actor):
            return {"allowed"}

    manager = make_workflow_manager(db, roles_manager=_Roles())
    actor = {"organization_id": _ORG_ID, "user_id": "u1", "roles": ["custom"]}

    listing = manager.list_state_machines_scoped_for_actor(
        actor, WorkflowListScopeRequest(scope="published")
    )
    assert [item.machine_name for item in listing.published_items] == ["allowed"]
    assert manager.get_workflow_by_row_id_for_actor(
        actor, WorkflowRowLookupRequest(row_id=allowed.id)
    ).machine_name == "allowed"
    with pytest.raises(NotFoundError):
        manager.get_workflow_by_row_id_for_actor(
            actor, WorkflowRowLookupRequest(row_id=hidden.id)
        )


def test_preflight_authorizes_the_hydrated_workflow(monkeypatch) -> None:
    db = _WorkflowLifecycleFakeDb()
    hidden = db.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name="hidden",
            version=1,
            is_active=True,
            definition=_minimal_definition("hidden"),
        ),
        organization_id=_ORG_ID,
    )

    class _Roles:
        @staticmethod
        def get_workflow_access_scope(_actor):
            return {"allowed"}

    manager = make_workflow_manager(db, roles_manager=_Roles())
    hidden_state = EntityState(
        entity_id="entity-1",
        entity_type="publish_entity",
        organization_id=_ORG_ID,
        machine_name="hidden",
        machine_version=1,
        workflow_id=hidden.id,
        current_state="start",
    )
    monkeypatch.setattr(
        manager,
        "_hydrate_state_with_id",
        lambda *_args, **_kwargs: (hidden_state, "state-1", hidden.id, None),
    )

    with pytest.raises(NotFoundError, match="hidden"):
        manager.preflight_transition_for_actor(
            {"organization_id": _ORG_ID, "user_id": "u1"},
            machine_name="allowed",
            current_state="start",
            entity_id="entity-1",
            trigger="complete",
            workflow_id=hidden.id,
        )


def test_draft_save_invalid_definition_returns_full_validation_issues() -> None:
    """Draft-save response should expose full ValidationIssue objects including code and severity."""
    db = _WorkflowLifecycleFakeDb()
    manager = make_workflow_manager(db)
    actor = {"organization_id": _ORG_ID, "user_id": "u1", "roles": ["admin"]}

    created = manager.create_workflow_draft_for_actor(
        actor,
        WorkflowDraftCreateRequest(name="Flow ABC", description="first draft"),
    )

    response = manager.update_workflow_draft_for_actor(
        actor,
        created.id,
        WorkflowDraftUpdateRequest(
            definition={
                **_definition_dict("frontend_bad_key", name="Broken Flow"),
                "entity_schema": {
                    "entity_type": "publish_entity",
                    "fields": [],
                },
                "transitions": [
                    {
                        "key": "start_to_end",
                        "trigger": "complete",
                        "label": "Complete",
                        "from": "start",
                        "to_state": "end",
                        "required_fields": [{"field": "missing_field", "required": True, "type": "string"}],
                        "guards": [],
                        "pre_transition_tasks": [],
                        "post_transition_tasks": [],
                        "auto_transition": None,
                        "sla_seconds": None,
                        "description": "Broken transition",
                    }
                ],
            }
        ),
    )

    assert response.is_valid is False
    assert len(response.validation_issues) == 1
    issue = response.validation_issues[0]
    assert "references undefined entity field 'missing_field'" in issue.message
    assert issue.code is not None
    assert "message" in issue.model_dump()


def test_manager_row_lookup_returns_exact_published_row_without_db() -> None:
    """Row lookup should return the exact published row when present."""
    db = _WorkflowLifecycleFakeDb()
    published = _published_record(
        row_id="pub-1",
        machine_name="wf_unit",
        version=1,
        definition=_minimal_definition("frontend_key"),
    )
    db.rows["pub-1"] = published

    manager = make_workflow_manager(db)
    actor = {"organization_id": _ORG_ID, "user_id": "u1", "roles": ["admin"]}
    got = manager.get_workflow_by_row_id_for_actor(actor, WorkflowRowLookupRequest(row_id="pub-1"))
    assert got.id == "pub-1"
    assert got.version == 1


def test_manager_row_lookup_returns_exact_draft_row_without_db() -> None:
    """Row lookup should return the exact draft row when present."""
    db = _WorkflowLifecycleFakeDb()
    draft = _draft_record(
        row_id="draft-1",
        machine_name="wf_unit_anchor",
        machine_key="wf_unit_anchor",
        definition=_definition_dict("frontend_machine_key"),
    )
    db.rows["draft-1"] = draft

    manager = make_workflow_manager(db)
    actor = {"organization_id": _ORG_ID, "user_id": "u1", "roles": ["admin"]}
    got = manager.get_workflow_by_row_id_for_actor(actor, WorkflowRowLookupRequest(row_id="draft-1"))
    assert got.id == "draft-1"
    assert got.version == 0


def test_manager_row_lookup_missing_id_raises_not_found_without_db() -> None:
    """Row lookup should raise not found when no matching row exists."""
    db = _WorkflowLifecycleFakeDb()
    manager = make_workflow_manager(db)
    actor = {"organization_id": _ORG_ID, "user_id": "u1", "roles": ["admin"]}
    with pytest.raises(NotFoundError):
        manager.get_workflow_by_row_id_for_actor(actor, WorkflowRowLookupRequest(row_id="missing-id"))


def _db_is_reachable() -> bool:
    """Return whether DATABASE_URL host appears reachable in this environment."""
    url = (
        os.environ.get("DATABASE_URL")
        or "postgresql://statemachine:statemachine@modular-db:5432/statemachine"
    )
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    try:
        socket.getaddrinfo(host, port)
    except OSError:
        return False
    return True


@pytest.fixture
def workflow_db_service():
    """WorkflowModelService bound to Postgres test DB, skipped if unreachable."""
    if not _db_is_reachable():
        pytest.skip("Postgres host is not reachable in this environment")

    url = (
        os.environ.get("DATABASE_URL")
        or "postgresql://statemachine:statemachine@modular-db:5432/statemachine"
    )
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "modular_backend")
    engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"options": f"-csearch_path={app_schema},public"},
    )
    session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)

    class _DbService:
        def __init__(self) -> None:
            self.engine = engine

        def get_db_session(self):
            return session_local()

    class _DbServiceManager:
        def __init__(self) -> None:
            self._svc = _DbService()

        def postgres_db_service(self):
            return self._svc

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM workflow_state_machines WHERE organization_id = ANY(:ids)"),
            {"ids": list(_TEST_ORG_IDS)},
        )

    svc = WorkflowModelService(database_service_manager=_DbServiceManager())
    yield svc

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM workflow_state_machines WHERE organization_id = ANY(:ids)"),
            {"ids": list(_TEST_ORG_IDS)},
        )
    engine.dispose()


def test_create_state_machine_published_without_db_manager_raises() -> None:
    """Published create should fail fast when DB service manager is unavailable."""
    svc = WorkflowModelService(database_service_manager=None)
    with pytest.raises(PersistenceError, match="Database service manager unavailable"):
        svc.create_state_machine_published(
            StateMachineCreateRequest(
                machine_name="pub_test_machine",
                version=1,
                is_active=False,
                definition=_minimal_definition(),
            ),
            organization_id=_ORG_ID,
        )


def test_create_state_machine_published_persists_row(workflow_db_service) -> None:
    """Published create should persist one active row with requested version."""
    created = workflow_db_service.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name="pub_test_machine",
            version=1,
            is_active=True,
            definition=_minimal_definition(),
        ),
        organization_id=_ORG_ID,
    )
    assert created.version == 1
    assert created.is_active is True
    assert created.machine_name == "pub_test_machine"


def test_create_state_machine_published_conflict_raises(workflow_db_service) -> None:
    """Creating duplicate machine_name+version should raise conflict."""
    workflow_db_service.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name="pub_test_machine",
            version=1,
            is_active=False,
            definition=_minimal_definition(),
        ),
        organization_id=_ORG_ID,
    )
    with pytest.raises(ConflictError):
        workflow_db_service.create_state_machine_published(
            StateMachineCreateRequest(
                machine_name="pub_test_machine",
                version=1,
                is_active=False,
                definition=_minimal_definition(),
            ),
            organization_id=_ORG_ID,
        )


def test_get_state_machine_by_row_id_returns_exact_row(workflow_db_service) -> None:
    """Row getter should return the exact draft or published row by row ID."""
    draft = workflow_db_service.create_state_machine_draft(
        organization_id=_ORG_ID,
        machine_key="pub_test_machine",
        machine_name="pub_test_machine",
        definition=_definition_dict(),
    )
    published = workflow_db_service.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name="pub_test_machine",
            version=1,
            is_active=False,
            definition=_minimal_definition(),
        ),
        organization_id=_ORG_ID,
    )

    got_draft = workflow_db_service.get_state_machine_by_row_id(
        organization_id=_ORG_ID,
        row_id=draft.id,
    )
    got_published = workflow_db_service.get_state_machine_by_row_id(
        organization_id=_ORG_ID,
        row_id=published.id,
    )
    assert got_draft is not None and got_draft.version == 0
    assert got_published is not None and got_published.version == 1


def test_list_state_machines_scope_filters(workflow_db_service) -> None:
    """Generic list should honor draft/published/all scopes."""
    workflow_db_service.create_state_machine_draft(
        organization_id=_ORG_ID,
        machine_key="wf_scope",
        machine_name="wf_scope",
        definition=_definition_dict("wf_scope"),
    )
    workflow_db_service.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name="wf_scope",
            version=1,
            is_active=False,
            definition=_minimal_definition("wf_scope"),
        ),
        organization_id=_ORG_ID,
    )

    drafts = workflow_db_service.list_state_machines(
        organization_id=_ORG_ID,
        machine_name="wf_scope",
        scope="draft",
    )
    published = workflow_db_service.list_state_machines(
        organization_id=_ORG_ID,
        machine_name="wf_scope",
        scope="published",
    )
    all_rows = workflow_db_service.list_state_machines(
        organization_id=_ORG_ID,
        machine_name="wf_scope",
        scope="all",
    )
    assert len(drafts) == 1 and drafts[0].version == 0
    assert len(published) == 1 and published[0].version == 1
    assert len(all_rows) == 2


def test_delete_state_machine_by_row_id_deletes_exact_row(workflow_db_service) -> None:
    """Row delete should remove only the targeted row, leaving siblings intact."""
    draft = workflow_db_service.create_state_machine_draft(
        organization_id=_ORG_ID,
        machine_key="wf_delete",
        machine_name="wf_delete",
        definition=_definition_dict("wf_delete"),
    )
    published = workflow_db_service.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name="wf_delete",
            version=1,
            is_active=False,
            definition=_minimal_definition("wf_delete"),
        ),
        organization_id=_ORG_ID,
    )

    deleted = workflow_db_service.delete_state_machine_by_row_id(
        organization_id=_ORG_ID,
        row_id=draft.id,
    )
    still_published = workflow_db_service.get_state_machine_by_row_id(
        organization_id=_ORG_ID,
        row_id=published.id,
    )

    assert deleted is not None and deleted.version == 0
    assert still_published is not None and still_published.version == 1


def test_draft_state_machine_crud_flow_preserves_machine_name(workflow_db_service) -> None:
    """Draft CRUD should overwrite draft content without changing the workflow family id."""
    created = workflow_db_service.create_state_machine_draft(
        organization_id=_ORG_ID,
        machine_key="wf_draft_crud",
        machine_name="wf_draft_crud",
        definition=_definition_dict("wf_draft_crud"),
    )
    assert created.id is not None
    assert created.version == 0

    updated_def = _definition_dict("frontend_draft_key")
    updated_def["description"] = "draft updated"
    updated = workflow_db_service.update_state_machine_draft(
        organization_id=_ORG_ID,
        row_id=created.id,
        definition=updated_def,
        canvas_metadata={"viewport": {"zoom": 1.25}},
    )
    assert updated is not None
    assert updated.description == "draft updated"
    assert updated.canvas_metadata == {"viewport": {"zoom": 1.25}}
    assert updated.machine_name == "wf_draft_crud"
    assert updated.machine_key == "frontend_draft_key"

    deleted = workflow_db_service.delete_state_machine_by_row_id(
        organization_id=_ORG_ID,
        row_id=created.id,
    )
    assert deleted is not None
    assert deleted.version == 0
    assert (
        workflow_db_service.get_state_machine_by_row_id(
            organization_id=_ORG_ID,
            row_id=created.id,
        )
        is None
    )


def test_published_state_machine_crud_flow(workflow_db_service) -> None:
    """Published CRUD: create, read, update, then delete by version>=1."""
    created = workflow_db_service.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name="wf_published_crud",
            version=1,
            is_active=False,
            definition=_minimal_definition("wf_published_crud"),
        ),
        organization_id=_ORG_ID,
    )
    assert created.id is not None
    assert created.version == 1

    fetched = workflow_db_service.get_state_machine_by_row_id(
        organization_id=_ORG_ID,
        row_id=created.id,
    )
    assert fetched is not None
    assert fetched.machine_name == "wf_published_crud"

    updated_def = _definition_dict("frontend_published_key")
    updated_def["description"] = "published updated"
    updated = workflow_db_service.update_state_machine_definition(
        organization_id=_ORG_ID,
        machine_name="wf_published_crud",
        version=1,
        definition=updated_def,
        canvas_metadata={"viewport": {"zoom": 1.5}},
    )
    assert updated is not None
    assert updated.description == "published updated"
    assert updated.canvas_metadata == {"viewport": {"zoom": 1.5}}

    deleted = workflow_db_service.delete_state_machine_by_row_id(
        organization_id=_ORG_ID,
        row_id=created.id,
    )
    assert deleted is not None
    assert deleted.version == 1
    assert (
        workflow_db_service.get_state_machine_by_row_id(
            organization_id=_ORG_ID,
            row_id=created.id,
        )
        is None
    )


def test_get_workflow_by_row_id_returns_exact_draft_row(workflow_db_service) -> None:
    """Manager row lookup should return the exact draft row without asking for version."""
    draft = workflow_db_service.create_state_machine_draft(
        organization_id=_ORG_ID,
        machine_key="wf_anchor",
        machine_name="wf_anchor",
        definition=_definition_dict("wf_anchor"),
    )
    workflow_db_service.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name="wf_anchor",
            version=1,
            is_active=False,
            definition=_minimal_definition("wf_anchor"),
        ),
        organization_id=_ORG_ID,
    )

    manager = make_workflow_manager(workflow_db_service)
    actor = {"organization_id": _ORG_ID, "user_id": "u1", "roles": ["admin"]}
    resolved = manager.get_workflow_by_row_id_for_actor(
        actor,
        WorkflowRowLookupRequest(row_id=draft.id),
    )
    assert resolved.id == draft.id
    assert resolved.version == 0


# ── Smart-delete unit tests (no DB required) ────────────────────────────────


def _make_manager_with_fake_db() -> tuple[WorkflowServiceManager, _WorkflowLifecycleFakeDb]:
    db = _WorkflowLifecycleFakeDb()
    manager = make_workflow_manager(db)
    return manager, db


_ACTOR = {"organization_id": _ORG_ID, "user_id": "u1", "roles": ["admin"]}


def test_delete_published_version_removes_row_without_db() -> None:
    """Deleting a published version should remove its row from the family."""
    manager, db = _make_manager_with_fake_db()
    pub = _published_record(
        row_id="pub-del-1",
        machine_name="wf_smart_del",
        version=1,
        definition=_minimal_definition(),
    )
    db.rows["pub-del-1"] = pub

    result = manager.delete_workflow_for_actor(_ACTOR, "pub-del-1")

    assert result.version == 1
    assert db.rows.get("pub-del-1") is None


def test_delete_draft_with_no_published_versions_removes_row_without_db() -> None:
    """Deleting a draft when no published versions exist should remove the row entirely."""
    manager, db = _make_manager_with_fake_db()
    draft = _draft_record(
        row_id="draft-only-1",
        machine_name="wf_draft_only",
        machine_key="wf_draft_only",
        definition=_definition_dict(),
    )
    db.rows["draft-only-1"] = draft

    result = manager.delete_workflow_for_actor(_ACTOR, "draft-only-1")

    assert result.version == 0
    assert db.rows.get("draft-only-1") is None


@pytest.mark.xfail(
    reason="Asserts the pre-soft-delete design: that archiving a draft with published versions resets its definition to a blank draft while keeping the row. Delete was deliberately changed to soft-delete — db_models.delete_state_machine_by_row_id only sets is_active=False and archived_at, and never rewrites the definition (identical on main). The current behaviour is already covered correctly by the archive tests in test_workflow_module.py (test_archive_draft_keeps_published_version / test_archive_published_keeps_draft). Out of scope for the definition-analysis refactor, which does not touch delete. See design_docs/workflow_refactor_carryover_findings.md CF-9.",
    strict=False,
)
def test_delete_draft_with_published_versions_resets_definition_without_db() -> None:
    """Deleting a draft when published versions exist should reset the definition but keep the row."""
    manager, db = _make_manager_with_fake_db()
    draft = _draft_record(
        row_id="draft-reset-1",
        machine_name="wf_has_published",
        machine_key="wf_has_published",
        definition=_definition_dict("old_machine_key", name="Old Draft Name"),
    )
    pub = _published_record(
        row_id="pub-anchor-1",
        machine_name="wf_has_published",
        version=1,
        definition=_minimal_definition(),
    )
    db.rows["draft-reset-1"] = draft
    db.rows["pub-anchor-1"] = pub

    result = manager.delete_workflow_for_actor(_ACTOR, "draft-reset-1")

    assert result.version == 0
    assert result.id == "draft-reset-1"
    assert db.rows.get("draft-reset-1") is not None, "row must be preserved"
    reset_def = db.rows["draft-reset-1"].definition
    assert reset_def.get("name") == "New Workflow"
    assert reset_def.get("transitions") == []


@pytest.mark.xfail(
    reason="Asserts the pre-soft-delete design: that archiving a draft with published versions resets its definition to a blank draft while keeping the row. Delete was deliberately changed to soft-delete — db_models.delete_state_machine_by_row_id only sets is_active=False and archived_at, and never rewrites the definition (identical on main). The current behaviour is already covered correctly by the archive tests in test_workflow_module.py (test_archive_draft_keeps_published_version / test_archive_published_keeps_draft). Out of scope for the definition-analysis refactor, which does not touch delete. See design_docs/workflow_refactor_carryover_findings.md CF-9.",
    strict=False,
)
def test_delete_draft_reset_allows_subsequent_update_without_db(monkeypatch) -> None:
    """After a draft reset, update_workflow_draft_for_actor must still accept the same row_id."""
    manager, db = _make_manager_with_fake_db()
    draft = _draft_record(
        row_id="draft-upd-after-reset",
        machine_name="wf_upd_after_reset",
        machine_key="wf_upd_after_reset",
        definition=_definition_dict(),
    )
    pub = _published_record(
        row_id="pub-upd-anchor",
        machine_name="wf_upd_after_reset",
        version=1,
        definition=_minimal_definition(),
    )
    db.rows["draft-upd-after-reset"] = draft
    db.rows["pub-upd-anchor"] = pub

    manager.delete_workflow_for_actor(_ACTOR, "draft-upd-after-reset")

    response = manager.update_workflow_draft_for_actor(
        _ACTOR,
        "draft-upd-after-reset",
        WorkflowDraftUpdateRequest(definition=_definition_dict("new_key", name="Rebuilt Draft")),
    )

    assert response.record.id == "draft-upd-after-reset"
    assert response.record.version == 0
    assert response.record.definition.get("name") == "Rebuilt Draft"


def test_delete_missing_row_raises_not_found_without_db() -> None:
    """Deleting a non-existent row_id should raise NotFoundError."""
    manager, _ = _make_manager_with_fake_db()
    with pytest.raises(NotFoundError, match="row_id 'ghost-row' was not found"):
        manager.delete_workflow_for_actor(_ACTOR, "ghost-row")


# ── Route-ordering tests (no DB required) ───────────────────────────────────




@pytest.fixture
def workflow_test_client(monkeypatch):
    """Real FastAPI router with auth patched and manager mocked — no DB needed."""
    from fastapi import APIRouter
    from fastapi.testclient import TestClient
    from unittest.mock import MagicMock
    import workflow.controller as _wc

    _actor = {"organization_id": _ORG_ID, "user_id": "u1", "roles": []}

    mock_manager = MagicMock()
    router = APIRouter()
    _wc.WorkflowRestController(workflow_service_manager=mock_manager).prepare(router, security=None)

    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)

    # Auth is injected as route-level FastAPI dependencies, not a patchable module helper.
    # The previous fixture monkeypatched `workflow.controller.get_current_actor_with_roles`,
    # which the 2026-07-15 auth refactor deleted. Overriding the real dependency objects
    # keeps the router genuine while supplying a fixed actor.
    for annotated in (_wc.WorkflowReadActor, _wc.WorkflowWriteActor):
        app.dependency_overrides[annotated.__metadata__[0].dependency] = lambda: _actor

    return TestClient(app, raise_server_exceptions=True), mock_manager


def test_default_template_not_shadowed_by_row_id_route(workflow_test_client) -> None:
    """`/default-template` must hit get_default_template_for_actor, not the /{row_id} handler."""
    client, mock_manager = workflow_test_client
    mock_manager.get_default_template_for_actor.return_value = _minimal_definition()

    response = client.get("/workflow-state-machines/default-template")

    assert response.status_code == 200
    mock_manager.get_default_template_for_actor.assert_called_once()
    mock_manager.get_workflow_by_row_id_for_actor.assert_not_called()


def test_list_not_shadowed_by_row_id_route(workflow_test_client) -> None:
    """`GET /workflow-state-machines` must hit list_state_machines_scoped_for_actor."""
    from workflow.models.response import WorkflowListResponse

    client, mock_manager = workflow_test_client
    mock_manager.list_state_machines_scoped_for_actor.return_value = WorkflowListResponse(
        scope="all", published_items=[], draft_items=[]
    )

    response = client.get("/workflow-state-machines")

    assert response.status_code == 200
    mock_manager.list_state_machines_scoped_for_actor.assert_called_once()
    mock_manager.get_workflow_by_row_id_for_actor.assert_not_called()


def test_row_id_route_resolves_workflow_row(workflow_test_client) -> None:
    """`GET /workflow-state-machines/{row_id}` must call get_workflow_by_row_id_for_actor."""
    client, mock_manager = workflow_test_client
    mock_manager.get_workflow_by_row_id_for_actor.return_value = _draft_record(
        row_id="some-uuid-row",
        machine_name="wf_test",
        machine_key="wf_test",
        definition=_definition_dict(),
    )

    response = client.get("/workflow-state-machines/some-uuid-row")

    assert response.status_code == 200
    mock_manager.get_workflow_by_row_id_for_actor.assert_called_once()
    mock_manager.get_default_template_for_actor.assert_not_called()
