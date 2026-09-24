"""Exhaustive coverage for the unified `audit_events` write/read pathway for
workflow transition attempts (succeeded/blocked/conflict).

Covers:
  - workflow/manager.py `_emit_transition_audit_event`, invoked from all three
    transition-attempt outcomes inside `execute_transition_for_actor`.
  - No new rows land in the legacy `audit.transition_attempts` table.
  - `audit/manager.py` `AuditServiceManager.list_audit_events_for_actor` (the
    sole read path) correctly returns TRANSITION-type rows unmodified —
    entity-scope 404/403, masking never touching them, pagination/filters.
  - A simulated audit-write failure during a real transition execution does
    NOT prevent the transition from succeeding.
  - The two deleted endpoints (`/entities/{id}/transitions/history`,
    `/entities/{id}/events/history`) 404 at the routing level.

Uses real Postgres via the `entities_db_service_manager` fixture (see
conftest.py) — no ORM mocking, real `WorkflowServiceManager` +
`EntitiesServiceManager` + `AuditEventsModelService` wiring.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from sqlalchemy import text

from audit.db_models import AuditEventsModelService
from audit.manager import AuditServiceManager
from common.enums import AuditMetadataType
from entities.db_models import EntitiesModelService
from entities.manager import EntitiesServiceManager
from entities.models.request import EntityRecordCreateRequest, EntityTypeCreateRequest
from exceptions import AuthorizationError, NotFoundError
from workflow.controller import WorkflowRestController
from workflow.db_models import WorkflowModelService
from workflow.manager import WorkflowServiceManager
from common.protocols import EntityAccessCheck
from workflow_manager_factory import (
    AllowAllEntityRolesManager,
    UnrestrictedRolesManager,
    AllowAllRolesDbModelService,
    make_workflow_manager,
)
from workflow.models.interface import (
    EntityField,
    EntitySchema,
    RequiredField,
    State,
    StateMachineDefinition,
    Transition,
    TransitionAuditEventType,
)
from workflow.models.request import StateMachineCreateRequest, TransitionExecuteRequest

from tests.conftest import ENTITIES_TEST_ORG_IDS

ORG = ENTITIES_TEST_ORG_IDS[0]
OTHER_ORG = ENTITIES_TEST_ORG_IDS[1]


# ── Test doubles ────────────────────────────────────────────────────────────


class _AlwaysAllowAuth:
    class _Decision:
        allowed = True
        reason = ""

    def check_access(self, _payload: dict[str, object]) -> "_AlwaysAllowAuth._Decision":
        return self._Decision()


class FakeRolesManager:
    """Deterministic `RolesServiceProtocol` double for audit-scope checks.

    `view_allowed` gates `check_entity_permission` (used by
    `AuditServiceManager._check_entity_scope`); visible/masked fields are
    irrelevant to transition rows (masking only ever touches ENTITY_UPDATED)
    so they default permissive.
    """

    def __init__(self, view_allowed: bool = True) -> None:
        self.view_allowed = view_allowed
        self.db_model_service = AllowAllRolesDbModelService()

    def evaluate_entity_access(self, *_args: Any, **_kwargs: Any) -> EntityAccessCheck:
        """Mirror `view_allowed` so entity-scope denial tests still deny."""
        return EntityAccessCheck(allowed=self.view_allowed, conditions=[])

    def get_workflow_access_scope(self, _actor: Any) -> set[str] | None:
        return None

    def get_visible_fields(self, db: Any, user_id: str, org_id: str, entity_type: str) -> list[str] | None:
        return None

    def get_masked_fields(self, db: Any, user_id: str, org_id: str, entity_type: str) -> list[str]:
        return []

    def get_editable_fields(self, db: Any, user_id: str, org_id: str, entity_type: str) -> list[str] | None:
        return None

    def check_entity_permission(
        self, db: Any, user_id: str, org_id: str, entity_type: str, action: str
    ) -> bool:
        return self.view_allowed


class FakeUserServiceManager:
    """Deterministic actor-display-info double used by `_resolve_transition_actor`."""

    def __init__(self, name: str = "Ada Lovelace", role: str = "recruiter") -> None:
        self.name = name
        self.role = role

    def get_actor_display_info(self, actor: dict[str, object]) -> tuple[str | None, str | None]:
        return self.name, self.role


class _AlwaysRaisingAuditEventsService:
    """Simulates the audit backend being entirely unavailable.

    Real `AuditEventsModelService.emit_audit_event` swallows its own
    failures and returns None; this double instead raises, so we can prove
    `_emit_transition_audit_event`'s own call site in `workflow/manager.py`
    also tolerates a failure that somehow escapes the db-layer's own
    try/except (defense in depth, per the audit-write-must-never-break-the-
    operation rule).
    """

    def emit_audit_event(self, **kwargs: object) -> None:
        raise RuntimeError("audit backend is down")


def _actor(user_id: str = "user-txn-test", organization_id: str = ORG) -> dict[str, object]:
    return {"user_id": user_id, "organization_id": organization_id, "roles": ["admin"]}


def _audit_schema() -> str:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "modular_backend")
    return f"{app_schema}_audit"


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def clean_transition_audit_tables(entities_db_service_manager):
    """Truncate audit_events, transition_attempts, and workflow/entity rows
    this suite creates for the test orgs, before and after each test."""
    audit_schema = _audit_schema()
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "modular_backend")
    runtime_schema = f"{app_schema}_runtime"
    definitions_schema = f"{app_schema}_definitions"
    engine = entities_db_service_manager.postgres_db_service().engine

    def _cleanup() -> None:
        with engine.begin() as conn:
            conn.execute(
                text(f'DELETE FROM "{audit_schema}".audit_events WHERE organization_id = ANY(:ids)'),
                {"ids": list(ENTITIES_TEST_ORG_IDS)},
            )
            conn.execute(
                text(f'DELETE FROM "{audit_schema}".transition_attempts WHERE organization_id = ANY(:ids)'),
                {"ids": list(ENTITIES_TEST_ORG_IDS)},
            )
            conn.execute(
                text(f'DELETE FROM "{audit_schema}".entity_events WHERE organization_id = ANY(:ids)'),
                {"ids": list(ENTITIES_TEST_ORG_IDS)},
            )
            conn.execute(
                text(f'DELETE FROM "{runtime_schema}".entity_state WHERE organization_id = ANY(:ids)'),
                {"ids": list(ENTITIES_TEST_ORG_IDS)},
            )
            conn.execute(
                text(f'DELETE FROM "{runtime_schema}".entities WHERE organization_id = ANY(:ids)'),
                {"ids": list(ENTITIES_TEST_ORG_IDS)},
            )
            conn.execute(
                text(
                    f'DELETE FROM "{definitions_schema}".entity_type_relations '
                    f"WHERE organization_id = ANY(:ids)"
                ),
                {"ids": list(ENTITIES_TEST_ORG_IDS)},
            )
            conn.execute(
                text(f'DELETE FROM "{definitions_schema}".entity_types WHERE organization_id = ANY(:ids)'),
                {"ids": list(ENTITIES_TEST_ORG_IDS)},
            )
            conn.execute(
                text("DELETE FROM workflow_state_machines WHERE organization_id = ANY(:ids)"),
                {"ids": list(ENTITIES_TEST_ORG_IDS)},
            )

    _cleanup()
    yield
    _cleanup()


def _count_transition_attempts(entities_db_service_manager, organization_id: str) -> int:
    """Query the legacy transition_attempts table directly to prove no new rows land there."""
    schema = _audit_schema()
    engine = entities_db_service_manager.postgres_db_service().engine
    with engine.connect() as conn:
        row = conn.execute(
            text(f'SELECT COUNT(*) FROM "{schema}".transition_attempts WHERE organization_id = :org_id'),
            {"org_id": organization_id},
        ).fetchone()
        return int(row[0])


def _query_audit_events(entities_db_service_manager, organization_id: str) -> list[dict]:
    """Read audit_events rows directly (bypassing the manager) for write-path assertions."""
    schema = _audit_schema()
    engine = entities_db_service_manager.postgres_db_service().engine
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT organization_id, metadata_type, entity_type, entity_id, event_type, "
                f"actor_id, actor_name, actor_role, actor_type, before_state, after_state, "
                f"idempotency_key, metadata "
                f'FROM "{schema}".audit_events WHERE organization_id = :org_id '
                f"ORDER BY event_timestamp ASC"
            ),
            {"org_id": organization_id},
        ).mappings().all()
        return [dict(r) for r in rows]


@pytest.fixture
def entities_db_service(entities_db_service_manager) -> EntitiesModelService:
    return EntitiesModelService(database_service_manager=entities_db_service_manager)


@pytest.fixture
def workflow_db_service(entities_db_service_manager) -> WorkflowModelService:
    return WorkflowModelService(entities_db_service_manager)


@pytest.fixture
def audit_events_service(entities_db_service_manager) -> AuditEventsModelService:
    return AuditEventsModelService(database_service_manager=entities_db_service_manager)


def _make_entities_manager(
    entities_db_service: EntitiesModelService,
    entities_db_service_manager: Any,
    audit_events_service: Any,
) -> EntitiesServiceManager:
    manager = EntitiesServiceManager(
        entities_db_service,
        database_service_manager=entities_db_service_manager,
        config=None,
        roles_manager=AllowAllEntityRolesManager(),
        audit_service_manager=AuditServiceManager(audit_events_service),
    )
    manager.start()
    return manager


def _make_workflow_manager(
    workflow_db_service: WorkflowModelService,
    entities_db_service_manager: Any,
    entities_manager: EntitiesServiceManager,
    audit_events_service: Any,
    *,
    roles_manager: Any = None,
) -> WorkflowServiceManager:
    manager = make_workflow_manager(
        workflow_db_service,
        entities_db_service_manager,
        entities_service_manager=entities_manager,
        roles_manager=roles_manager or UnrestrictedRolesManager(),
        user_service_manager=FakeUserServiceManager(),
        audit_events_service=audit_events_service,
    )
    manager.start()
    return manager


def _make_audit_manager(
    audit_events_service: AuditEventsModelService,
    entities_db_service: EntitiesModelService,
    roles_manager: Any,
) -> AuditServiceManager:
    manager = AuditServiceManager(
        audit_events_service,
        roles_manager=roles_manager or UnrestrictedRolesManager(),
        entities_service=entities_db_service,
    )
    manager.start()
    return manager


def _gated_definition(machine_key: str, entity_type: str) -> StateMachineDefinition:
    """One workflow: APPLIED -> SCREENING (requires 'approver' field), single state."""
    return StateMachineDefinition(
        machine_key=machine_key,
        name=machine_key,
        description="",
        entity_type=entity_type,
        entity_schema=EntitySchema(
            entity_type=entity_type,
            fields=[EntityField(field="approver", type="string", required=False)],
        ),
        states=[
            State(name="APPLIED", tags=["initial"], order=1),
            State(name="SCREENING", tags=[], order=2),
            State(name="TERMINAL", tags=["terminal"], order=3),
        ],
        initial_state="APPLIED",
        transitions=[
            Transition(
                key="advance",
                trigger="advance",
                label="Advance",
                from_state="APPLIED",
                to_state="SCREENING",
                required_fields=[RequiredField(field="approver", required=True)],
                guards=[],
            ),
            Transition(
                key="finish",
                trigger="finish",
                label="Finish",
                from_state="SCREENING",
                to_state="TERMINAL",
                required_fields=[],
                guards=[],
            ),
        ],
    )


def _seed_workflow_entity(
    entities_manager: EntitiesServiceManager,
    workflow_manager: WorkflowServiceManager,
    *,
    org: str = ORG,
    machine_key: str = "txn_audit_wf",
    entity_type_name: str = "TxnAuditType",
) -> tuple[str, str]:
    """Create entity_type + published workflow + entity + enrollment. Returns (entity_id, workflow_row_id)."""
    et = entities_manager.create_entity_type_for_actor(
        _actor(organization_id=org),
        EntityTypeCreateRequest(name=entity_type_name, schema_definition={"fields": []}),
    )
    machine = workflow_manager.workflow_db.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name=machine_key,
            version=1,
            is_active=True,
            definition=_gated_definition(machine_key, entity_type_name),
        ),
        organization_id=org,
    )
    record = entities_manager.create_entity_record_for_actor(
        _actor(organization_id=org),
        EntityRecordCreateRequest(entity_type_id=et.entity_type_id, data={"identifier": "txn-audit-001"}),
    )
    workflow_manager.enroll_entity_for_actor(
        _actor(organization_id=org), machine_name=machine_key, entity_id=record.entity_id
    )
    return record.entity_id, machine.id


@pytest.fixture
def txn_env(entities_db_service_manager, clean_transition_audit_tables):
    """Fully wired (entities_manager, workflow_manager, audit_events_service, entities_db_service)."""
    entities_db_service = EntitiesModelService(database_service_manager=entities_db_service_manager)
    workflow_db_service = WorkflowModelService(entities_db_service_manager)
    audit_events_service = AuditEventsModelService(database_service_manager=entities_db_service_manager)
    entities_manager = _make_entities_manager(
        entities_db_service, entities_db_service_manager, audit_events_service
    )
    workflow_manager = _make_workflow_manager(
        workflow_db_service, entities_db_service_manager, entities_manager, audit_events_service
    )
    return {
        "entities_manager": entities_manager,
        "workflow_manager": workflow_manager,
        "audit_events_service": audit_events_service,
        "entities_db_service": entities_db_service,
        "db_service_manager": entities_db_service_manager,
    }


# ── Write path: SUCCEEDED ────────────────────────────────────────────────────


def test_execute_transition_succeeded_writes_audit_event_with_correct_shape(txn_env) -> None:
    """A successful transition writes exactly one TRANSITION_SUCCEEDED row with
    before/after state, resolved entity_type, actor identity, and metadata."""
    entity_id, workflow_row_id = _seed_workflow_entity(
        txn_env["entities_manager"], txn_env["workflow_manager"]
    )
    txn_env["workflow_manager"].execute_transition_for_actor(
        _actor(),
        entity_id,
        TransitionExecuteRequest(entity_id=entity_id, trigger="advance", inputs={"approver": "mgr-1"}),
    )

    rows = _query_audit_events(txn_env["db_service_manager"], ORG)
    succeeded = [r for r in rows if r["event_type"] == TransitionAuditEventType.SUCCEEDED]
    assert len(succeeded) == 1
    row = succeeded[0]
    assert row["metadata_type"] == AuditMetadataType.TRANSITION.value
    assert row["entity_id"] == entity_id
    assert row["entity_type"] == "TxnAuditType"
    assert row["before_state"] == "APPLIED"
    assert row["after_state"] == "SCREENING"
    assert row["actor_id"] == "user-txn-test"
    assert row["actor_name"] == "Ada Lovelace"
    assert row["actor_role"] == "recruiter"
    assert row["actor_type"] == "user"
    metadata = row["metadata"]
    assert metadata["workflow_id"] == workflow_row_id
    assert metadata["trigger"] == "advance"
    assert metadata["status"] == "succeeded"
    assert metadata["machine_name"] == "txn_audit_wf"
    assert metadata["machine_version"] == 1
    assert metadata["inputs"] == {"approver": "mgr-1"}
    assert "outputs" in metadata and metadata["outputs"] is not None
    assert "blocked_reasons" not in metadata


def test_execute_transition_succeeded_writes_no_row_to_transition_attempts(txn_env) -> None:
    """Hard cutover: transition_attempts must receive zero new rows."""
    entity_id, _ = _seed_workflow_entity(txn_env["entities_manager"], txn_env["workflow_manager"])
    before = _count_transition_attempts(txn_env["db_service_manager"], ORG)
    txn_env["workflow_manager"].execute_transition_for_actor(
        _actor(),
        entity_id,
        TransitionExecuteRequest(entity_id=entity_id, trigger="advance", inputs={"approver": "mgr-1"}),
    )
    after = _count_transition_attempts(txn_env["db_service_manager"], ORG)
    assert before == 0
    assert after == 0


def test_execute_transition_replays_idempotent_result_from_audit_events(txn_env) -> None:
    """A retried transition with the same idempotency_key must replay the cached
    SUCCEEDED result from audit_events, not re-execute the transition. Guards
    against the regression where dropping transition_attempts writes silently
    broke idempotent replay (it used to read from that table)."""
    entity_id, _ = _seed_workflow_entity(txn_env["entities_manager"], txn_env["workflow_manager"])
    request = TransitionExecuteRequest(
        entity_id=entity_id,
        trigger="advance",
        inputs={"approver": "mgr-1"},
        idempotency_key="retry-key-1",
    )
    first = txn_env["workflow_manager"].execute_transition_for_actor(_actor(), entity_id, request)
    assert first.idempotent is False
    assert first.to_state == "SCREENING"

    second = txn_env["workflow_manager"].execute_transition_for_actor(_actor(), entity_id, request)
    assert second.idempotent is True
    assert second.to_state == "SCREENING"
    assert second.transition_id == first.transition_id

    rows = _query_audit_events(txn_env["db_service_manager"], ORG)
    succeeded = [r for r in rows if r["event_type"] == TransitionAuditEventType.SUCCEEDED]
    assert len(succeeded) == 1


def test_execute_transition_system_initiated_records_system_actor(txn_env) -> None:
    """System-initiated transitions record actor_type=system, actor_id=None."""
    entity_id, _ = _seed_workflow_entity(txn_env["entities_manager"], txn_env["workflow_manager"])
    # Move to SCREENING first (requires an actor input), then run a system transition.
    txn_env["workflow_manager"].execute_transition_for_actor(
        _actor(),
        entity_id,
        TransitionExecuteRequest(entity_id=entity_id, trigger="advance", inputs={"approver": "mgr-1"}),
    )
    txn_env["workflow_manager"].execute_transition_system(ORG, entity_id, "finish")

    rows = _query_audit_events(txn_env["db_service_manager"], ORG)
    succeeded = [r for r in rows if r["event_type"] == TransitionAuditEventType.SUCCEEDED]
    system_row = next(r for r in succeeded if r["after_state"] == "TERMINAL")
    assert system_row["actor_type"] == "system"
    # `execute_transition_system` sets user_id="system" as a sentinel; the
    # resolved display name/role still short-circuit to the System identity
    # because `_resolve_transition_actor` is keyed off `is_system`, not actor_id.
    assert system_row["actor_id"] == "system"
    assert system_row["actor_name"] == "System"
    assert system_row["actor_role"] == "SYSTEM"


# ── Write path: BLOCKED ──────────────────────────────────────────────────────


def test_execute_transition_blocked_writes_audit_event_with_blocked_reasons(txn_env) -> None:
    """A guard/required-field failure writes TRANSITION_BLOCKED with blocked_reasons
    both top-level and inside outputs, and does not advance entity state."""
    entity_id, workflow_row_id = _seed_workflow_entity(
        txn_env["entities_manager"], txn_env["workflow_manager"]
    )
    with pytest.raises(Exception):
        txn_env["workflow_manager"].execute_transition_for_actor(
            _actor(),
            entity_id,
            TransitionExecuteRequest(entity_id=entity_id, trigger="advance", inputs={}),
        )

    rows = _query_audit_events(txn_env["db_service_manager"], ORG)
    blocked = [r for r in rows if r["event_type"] == TransitionAuditEventType.BLOCKED]
    assert len(blocked) == 1
    row = blocked[0]
    assert row["metadata_type"] == AuditMetadataType.TRANSITION.value
    assert row["before_state"] == "APPLIED"
    assert row["after_state"] == "SCREENING"
    assert row["entity_type"] == "TxnAuditType"
    metadata = row["metadata"]
    assert metadata["workflow_id"] == workflow_row_id
    assert metadata["status"] == "blocked"
    assert metadata["blocked_reasons"] == ["required field 'approver' is missing or invalid"]
    assert "guard_evaluations" in metadata


def test_execute_transition_blocked_writes_no_row_to_transition_attempts(txn_env) -> None:
    """Hard cutover applies to BLOCKED outcomes too."""
    entity_id, _ = _seed_workflow_entity(txn_env["entities_manager"], txn_env["workflow_manager"])
    with pytest.raises(Exception):
        txn_env["workflow_manager"].execute_transition_for_actor(
            _actor(),
            entity_id,
            TransitionExecuteRequest(entity_id=entity_id, trigger="advance", inputs={}),
        )
    assert _count_transition_attempts(txn_env["db_service_manager"], ORG) == 0


# ── Write path: CONFLICT ─────────────────────────────────────────────────────


def _force_stale_hydrate(workflow_manager: WorkflowServiceManager) -> None:
    """Patch `_hydrate_state_with_id` for one manager instance so it returns a
    snapshot with `state_version=0` regardless of the DB's real current
    version — the only deterministic way to reproduce an optimistic-lock
    conflict without real concurrency, since a single sequential call always
    hydrates fresh and therefore can never observe its own staleness."""
    original = workflow_manager._hydrate_state_with_id

    def _stale(organization_id: str, entity_id: str, **kwargs):
        entity_state, state_id, workflow_id, machine = original(organization_id, entity_id)
        if entity_state is None:
            return entity_state, state_id, workflow_id, machine
        stale_state = entity_state.model_copy(update={"state_version": 0})
        return stale_state, state_id, workflow_id, machine

    workflow_manager._hydrate_state_with_id = _stale


def test_execute_transition_conflict_writes_audit_event(txn_env) -> None:
    """A stale optimistic-lock version writes TRANSITION_CONFLICT with a
    descriptive blocked_reasons entry and raises ConflictError."""
    entity_id, workflow_row_id = _seed_workflow_entity(
        txn_env["entities_manager"], txn_env["workflow_manager"]
    )
    entities_db_service: EntitiesModelService = txn_env["entities_db_service"]
    states = entities_db_service.list_entity_states_for_entity(organization_id=ORG, entity_id=entity_id)
    assert len(states) == 1
    state_id = states[0].state_id

    # Advance the row's real state_version to 1 so the manager's (patched)
    # stale hydrate at state_version=0 no longer matches the DB.
    bumped = entities_db_service.transition_entity_state(
        organization_id=ORG,
        state_id=state_id,
        expected_state_version=0,
        next_state="APPLIED",
        state_entered_at=datetime.now(),
        last_transition_at=datetime.now(),
        sla_due_at=None,
    )
    assert bumped is not None
    assert bumped.state_version == 1
    _force_stale_hydrate(txn_env["workflow_manager"])

    from exceptions import ConflictError

    with pytest.raises(ConflictError):
        txn_env["workflow_manager"].execute_transition_for_actor(
            _actor(),
            entity_id,
            TransitionExecuteRequest(entity_id=entity_id, trigger="advance", inputs={"approver": "mgr-1"}),
        )

    rows = _query_audit_events(txn_env["db_service_manager"], ORG)
    conflict = [r for r in rows if r["event_type"] == TransitionAuditEventType.CONFLICT]
    assert len(conflict) == 1
    row = conflict[0]
    assert row["metadata_type"] == AuditMetadataType.TRANSITION.value
    assert row["entity_type"] == "TxnAuditType"
    metadata = row["metadata"]
    assert metadata["workflow_id"] == workflow_row_id
    assert metadata["status"] == "conflict"
    assert metadata["blocked_reasons"] == ["workflow entity state version conflict"]


def test_execute_transition_conflict_writes_no_row_to_transition_attempts(txn_env) -> None:
    """Hard cutover applies to CONFLICT outcomes too."""
    entity_id, _ = _seed_workflow_entity(txn_env["entities_manager"], txn_env["workflow_manager"])
    entities_db_service: EntitiesModelService = txn_env["entities_db_service"]
    states = entities_db_service.list_entity_states_for_entity(organization_id=ORG, entity_id=entity_id)
    state_id = states[0].state_id
    entities_db_service.transition_entity_state(
        organization_id=ORG,
        state_id=state_id,
        expected_state_version=0,
        next_state="APPLIED",
        state_entered_at=datetime.now(),
        last_transition_at=datetime.now(),
        sla_due_at=None,
    )
    _force_stale_hydrate(txn_env["workflow_manager"])

    from exceptions import ConflictError

    with pytest.raises(ConflictError):
        txn_env["workflow_manager"].execute_transition_for_actor(
            _actor(),
            entity_id,
            TransitionExecuteRequest(entity_id=entity_id, trigger="advance", inputs={"approver": "mgr-1"}),
        )
    assert _count_transition_attempts(txn_env["db_service_manager"], ORG) == 0


# ── Audit-write failure must never break the transition (rule 4) ────────────


def _use_raising_audit_service(workflow_manager) -> None:
    """Point the audit writer at a service that always raises.

    The transition-audit service is the only holder of the writer, so this is the single place
    to patch. When the manager also kept a reference, patching one and not the other left the
    real writer in play and the test passed while proving nothing.
    """
    workflow_manager.transition_audit.audit_events_service = _AlwaysRaisingAuditEventsService()


def test_transition_succeeds_even_when_audit_write_raises(txn_env) -> None:
    """Swap in an audit_events_service that always raises. The transition must
    still succeed and return correctly — the audit failure is caught and
    logged, never propagated."""
    entity_id, _ = _seed_workflow_entity(txn_env["entities_manager"], txn_env["workflow_manager"])
    _use_raising_audit_service(txn_env["workflow_manager"])

    response = txn_env["workflow_manager"].execute_transition_for_actor(
        _actor(),
        entity_id,
        TransitionExecuteRequest(entity_id=entity_id, trigger="advance", inputs={"approver": "mgr-1"}),
    )

    assert response.entity_id == entity_id
    assert response.from_state == "APPLIED"
    assert response.to_state == "SCREENING"

    # Underlying state was actually committed despite the audit failure.
    entities_db_service: EntitiesModelService = txn_env["entities_db_service"]
    states = entities_db_service.list_entity_states_for_entity(organization_id=ORG, entity_id=entity_id)
    assert states[0].current_state == "SCREENING"

    # And, naturally, no row landed in audit_events for this transition either.
    rows = _query_audit_events(txn_env["db_service_manager"], ORG)
    assert not any(r["event_type"] == TransitionAuditEventType.SUCCEEDED for r in rows)


def test_transition_blocked_still_raises_validation_error_when_audit_write_raises(txn_env) -> None:
    """A raising audit backend must not mask the real BLOCKED outcome (ValidationError)."""
    entity_id, _ = _seed_workflow_entity(txn_env["entities_manager"], txn_env["workflow_manager"])
    _use_raising_audit_service(txn_env["workflow_manager"])

    from exceptions import ValidationError

    with pytest.raises(ValidationError):
        txn_env["workflow_manager"].execute_transition_for_actor(
            _actor(),
            entity_id,
            TransitionExecuteRequest(entity_id=entity_id, trigger="advance", inputs={}),
        )


# ── Read path: GET /audit-events already handles TRANSITION rows ────────────


def test_list_audit_events_for_actor_returns_transition_rows_for_entity(txn_env) -> None:
    """Reading through the unmodified, generic `list_audit_events_for_actor`
    returns transition rows scoped to the entity, newest-first, unmasked."""
    entity_id, _ = _seed_workflow_entity(txn_env["entities_manager"], txn_env["workflow_manager"])
    txn_env["workflow_manager"].execute_transition_for_actor(
        _actor(),
        entity_id,
        TransitionExecuteRequest(entity_id=entity_id, trigger="advance", inputs={"approver": "mgr-1"}),
    )
    txn_env["workflow_manager"].execute_transition_system(ORG, entity_id, "finish")

    roles_manager = FakeRolesManager(view_allowed=True)
    audit_manager = _make_audit_manager(
        txn_env["audit_events_service"], txn_env["entities_db_service"], roles_manager
    )
    result = audit_manager.list_audit_events_for_actor(
        _actor(), entity_id=entity_id, metadata_type=AuditMetadataType.TRANSITION.value
    )

    assert result.total == 2
    event_types = {item.event_type for item in result.items}
    assert event_types == {TransitionAuditEventType.SUCCEEDED.value}
    for item in result.items:
        assert item.metadata_type == AuditMetadataType.TRANSITION.value
        assert item.before_state is not None
        assert item.after_state is not None
    # newest-first
    assert result.items[0].after_state == "TERMINAL"
    assert result.items[1].after_state == "SCREENING"


def test_list_audit_events_for_actor_filters_by_event_type(txn_env) -> None:
    """`event_type` query filter narrows results to just BLOCKED rows."""
    entity_id, _ = _seed_workflow_entity(txn_env["entities_manager"], txn_env["workflow_manager"])
    with pytest.raises(Exception):
        txn_env["workflow_manager"].execute_transition_for_actor(
            _actor(),
            entity_id,
            TransitionExecuteRequest(entity_id=entity_id, trigger="advance", inputs={}),
        )
    txn_env["workflow_manager"].execute_transition_for_actor(
        _actor(),
        entity_id,
        TransitionExecuteRequest(entity_id=entity_id, trigger="advance", inputs={"approver": "mgr-1"}),
    )

    roles_manager = FakeRolesManager(view_allowed=True)
    audit_manager = _make_audit_manager(
        txn_env["audit_events_service"], txn_env["entities_db_service"], roles_manager
    )
    result = audit_manager.list_audit_events_for_actor(
        _actor(), entity_id=entity_id, event_type=TransitionAuditEventType.BLOCKED.value
    )
    assert result.total == 1
    assert result.items[0].event_type == TransitionAuditEventType.BLOCKED.value


def test_list_audit_events_for_actor_paginates_transition_rows(txn_env) -> None:
    """limit/offset page through transition rows without duplication or gaps."""
    entity_id, workflow_row_id = _seed_workflow_entity(
        txn_env["entities_manager"], txn_env["workflow_manager"]
    )
    # Generate 5 BLOCKED attempts (cheap, repeatable, doesn't advance state).
    for _ in range(5):
        with pytest.raises(Exception):
            txn_env["workflow_manager"].execute_transition_for_actor(
                _actor(),
                entity_id,
                TransitionExecuteRequest(entity_id=entity_id, trigger="advance", inputs={}),
            )

    roles_manager = FakeRolesManager(view_allowed=True)
    audit_manager = _make_audit_manager(
        txn_env["audit_events_service"], txn_env["entities_db_service"], roles_manager
    )
    common_kwargs = {
        "entity_id": entity_id,
        "metadata_type": AuditMetadataType.TRANSITION.value,
    }
    page1 = audit_manager.list_audit_events_for_actor(_actor(), limit=2, offset=0, **common_kwargs)
    page2 = audit_manager.list_audit_events_for_actor(_actor(), limit=2, offset=2, **common_kwargs)
    assert page1.total == 5
    assert page2.total == 5
    assert len(page1.items) == 2
    assert len(page2.items) == 2
    ids_page1 = {item.id for item in page1.items}
    ids_page2 = {item.id for item in page2.items}
    assert ids_page1.isdisjoint(ids_page2)


def test_list_audit_events_for_actor_missing_entity_raises_not_found(txn_env) -> None:
    """404 guard on `_check_entity_scope` still applies to transition reads."""
    roles_manager = FakeRolesManager(view_allowed=True)
    audit_manager = _make_audit_manager(
        txn_env["audit_events_service"], txn_env["entities_db_service"], roles_manager
    )
    with pytest.raises(NotFoundError):
        audit_manager.list_audit_events_for_actor(_actor(), entity_id="does-not-exist")


def test_list_audit_events_for_actor_denies_view_without_permission(txn_env) -> None:
    """403 guard on `_check_entity_scope` still applies to transition reads."""
    entity_id, _ = _seed_workflow_entity(txn_env["entities_manager"], txn_env["workflow_manager"])
    roles_manager = FakeRolesManager(view_allowed=False)
    audit_manager = _make_audit_manager(
        txn_env["audit_events_service"], txn_env["entities_db_service"], roles_manager
    )
    with pytest.raises(AuthorizationError):
        audit_manager.list_audit_events_for_actor(_actor(), entity_id=entity_id)


def test_masking_never_touches_transition_rows(txn_env) -> None:
    """`_mask_entity_updated_items` only ever inspects ENTITY_UPDATED rows —
    prove a TRANSITION row's metadata (including blocked_reasons) survives
    a read completely untouched, even when the same read also returns
    ENTITY-type rows (ENTITY_CREATED, ENTITY_ENROLLED) for the same entity."""
    entity_id, _ = _seed_workflow_entity(txn_env["entities_manager"], txn_env["workflow_manager"])
    with pytest.raises(Exception):
        txn_env["workflow_manager"].execute_transition_for_actor(
            _actor(),
            entity_id,
            TransitionExecuteRequest(entity_id=entity_id, trigger="advance", inputs={}),
        )

    roles_manager = FakeRolesManager(view_allowed=True)
    audit_manager = _make_audit_manager(
        txn_env["audit_events_service"], txn_env["entities_db_service"], roles_manager
    )
    result = audit_manager.list_audit_events_for_actor(_actor(), entity_id=entity_id)
    assert result.total == 3
    transition_items = [item for item in result.items if item.metadata_type == AuditMetadataType.TRANSITION.value]
    assert len(transition_items) == 1
    item = transition_items[0]
    assert item.event_type == TransitionAuditEventType.BLOCKED.value
    assert item.metadata["blocked_reasons"] == ["required field 'approver' is missing or invalid"]


def test_list_audit_events_for_actor_org_isolation(txn_env) -> None:
    """An actor in a different org cannot see another org's entity — 404, not leaked data."""
    entity_id, _ = _seed_workflow_entity(txn_env["entities_manager"], txn_env["workflow_manager"])
    txn_env["workflow_manager"].execute_transition_for_actor(
        _actor(),
        entity_id,
        TransitionExecuteRequest(entity_id=entity_id, trigger="advance", inputs={"approver": "mgr-1"}),
    )
    roles_manager = FakeRolesManager(view_allowed=True)
    audit_manager = _make_audit_manager(
        txn_env["audit_events_service"], txn_env["entities_db_service"], roles_manager
    )
    with pytest.raises(NotFoundError):
        audit_manager.list_audit_events_for_actor(_actor(organization_id=OTHER_ORG), entity_id=entity_id)


# ── Deleted endpoints 404 at the routing level ───────────────────────────────


@pytest.fixture
def workflow_test_client(txn_env) -> TestClient:
    """A minimal FastAPI app with only the workflow router mounted, no auth
    dependency override needed since we're only probing route existence."""
    app_router = APIRouter()
    controller = WorkflowRestController(txn_env["workflow_manager"])
    controller.prepare(app_router)
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(app_router)
    return TestClient(app, raise_server_exceptions=False)


def test_transitions_history_endpoint_is_gone(workflow_test_client) -> None:
    """`GET /entities/{id}/transitions/history` no longer exists — plain FastAPI 404."""
    response = workflow_test_client.get("/entities/some-entity/transitions/history")
    assert response.status_code == 404


def test_events_history_endpoint_is_gone(workflow_test_client) -> None:
    """`GET /entities/{id}/events/history` no longer exists — plain FastAPI 404."""
    response = workflow_test_client.get("/entities/some-entity/events/history")
    assert response.status_code == 404
