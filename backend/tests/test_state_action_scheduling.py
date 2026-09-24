"""Coverage for state-linked action runs and SLA signals.

A workflow state can carry `on_state_actions`. When a record arrives in that state, the engine
writes one `action_runs` row — the instruction a background worker later picks up and executes.
A state can also carry `sla_seconds`, which schedules a `signal.fire` run to be delivered if the
record is still sitting there when the deadline passes. A user can additionally re-run a state's
action manually.

None of that had test coverage, and it once died silently for a whole release: a refactor made
the creation call raise, a broad `except` logged one line, and every transition still reported
success. So these tests assert the **row in the database**, never the response — the response
says "succeeded" either way, which is precisely how the outage went unnoticed.

What each thing means, since the config is a contract the worker reads:

  * `idempotency_key` — identifies one arrival, so replaying a transition cannot double-run an
    action. Entry uses `{entity}:{state}:{transition}:v{state_version}:a0`; a manual rerun uses
    `{entity}:{state}:rerun:{run_id}` because a rerun is deliberately a new attempt.
  * `chain_id` / `state_action_index` / `state_action_total` — a state's actions run as a chain.
    Only the first is created up front; the worker creates the next one as each finishes.
  * `origin_state` / `origin_state_version` — what the action was scheduled for, so a run that
    arrives late can tell it is stale.
  * `isolated_rerun` — true only for a manual rerun, which runs one action without its chain.

Uses real Postgres. `WorkflowModelService.create_action_run` returns silently in memory mode, so
`test_canary_rows_are_really_written` guards the whole file: if it fails, nothing else here is
meaningful.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from workflow_manager_factory import (
    AllowAllEntityRolesManager,
    UnrestrictedRolesManager,
    make_workflow_manager,
)

from audit.db_models import AuditEventsModelService
from audit.manager import AuditServiceManager
from entities.db_models import EntitiesModelService
from entities.manager import EntitiesServiceManager
from entities.models.request import EntityRecordCreateRequest, EntityTypeCreateRequest
from exceptions import ConflictError, NotFoundError, ValidationError
from tests.conftest import ENTITIES_TEST_ORG_IDS
from workflow.db_models import WorkflowModelService
from workflow.models.interface import (
    EntityField,
    EntitySchema,
    RequiredField,
    State,
    StateAction,
    StateMachineDefinition,
    Transition,
)
from workflow.models.request import StateMachineCreateRequest, TransitionExecuteRequest
from workflow.services.state_action_scheduling import StateActionSchedulingService

ORG = ENTITIES_TEST_ORG_IDS[0]
PRIMARY_KIND = "agent.run"
SECOND_KIND = "notify.send"
SLA_SECONDS = 3600
ACTION_RUNS_TABLE = "modular_backend.action_runs"
AUDIT_EVENTS_TABLE = (
    f"{os.environ.get('POSTGRES_APP_SCHEMA', 'modular_backend')}_audit.audit_events"
)


def _actor(user_id: str = "user-sas-test") -> dict[str, object]:
    return {"user_id": user_id, "organization_id": ORG, "roles": ["admin"]}


def _actions() -> list[StateAction]:
    """Two actions, so `state_action_total` is meaningfully greater than one."""
    return [
        StateAction(
            kind=PRIMARY_KIND,
            config={"agent_slug": "screener"},
            outcome_triggers={"passed": "advance"},
            failure_policy={"on_error": "halt"},
        ),
        StateAction(kind=SECOND_KIND, config={"template": "second"}),
    ]


def _definition(
    machine_key: str,
    entity_type: str,
    *,
    actions_on_screening: bool = True,
    actions_on_initial: bool = False,
    sla_on_screening: bool = False,
) -> StateMachineDefinition:
    """APPLIED -> SCREENING -> TERMINAL, with actions and SLA placed per the test's need."""
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
            State(
                name="APPLIED",
                tags=["initial"],
                order=1,
                on_state_actions=_actions() if actions_on_initial else [],
            ),
            State(
                name="SCREENING",
                order=2,
                on_state_actions=_actions() if actions_on_screening else [],
                sla_seconds=SLA_SECONDS if sla_on_screening else None,
            ),
            State(name="TERMINAL", tags=["terminal"], order=3),
        ],
        initial_state="APPLIED",
        transitions=[
            Transition(
                key="advance", trigger="advance", label="Advance",
                from_state="APPLIED", to_state="SCREENING",
                required_fields=[RequiredField(field="approver", required=True)],
                guards=[],
            ),
            Transition(
                key="finish", trigger="finish", label="Finish",
                from_state="SCREENING", to_state="TERMINAL",
                required_fields=[], guards=[],
            ),
        ],
    )


@pytest.fixture
def sas_env(entities_db_service_manager):
    """Real-database workflow and entities managers, wired through the shared factory."""
    entities_db = EntitiesModelService(database_service_manager=entities_db_service_manager)
    workflow_db = WorkflowModelService(entities_db_service_manager)
    audit_events = AuditEventsModelService(database_service_manager=entities_db_service_manager)

    entities_manager = EntitiesServiceManager(
        entities_db,
        database_service_manager=entities_db_service_manager,
        config=None,
        roles_manager=AllowAllEntityRolesManager(),
        audit_service_manager=AuditServiceManager(audit_events),
    )
    entities_manager.start()

    workflow_manager = make_workflow_manager(
        workflow_db,
        entities_db_service_manager,
        entities_service_manager=entities_manager,
        roles_manager=UnrestrictedRolesManager(),
        audit_events_service=audit_events,
    )
    workflow_manager.start()

    return {
        "workflow_manager": workflow_manager,
        "entities_manager": entities_manager,
        "db": entities_db_service_manager,
    }


def _seed(env, machine_key: str, entity_type: str, *, enroll: bool = True, **definition_kwargs):
    """Create the entity type, publish the workflow, create an entity, optionally enroll it.

    Names carry a per-run suffix. Entity types are unique per organization, so fixed names would
    make this file pass once and fail on every run after.
    """
    suffix = uuid.uuid4().hex[:8]
    machine_key = f"{machine_key}_{suffix}"
    entity_type = f"{entity_type}{suffix}"
    env["machine_key"] = machine_key
    entity_type_record = env["entities_manager"].create_entity_type_for_actor(
        _actor(), EntityTypeCreateRequest(name=entity_type, schema_definition={"fields": []})
    )
    env["workflow_manager"].workflow_db.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name=machine_key,
            version=1,
            is_active=True,
            definition=_definition(machine_key, entity_type, **definition_kwargs),
        ),
        organization_id=ORG,
    )
    record = env["entities_manager"].create_entity_record_for_actor(
        _actor(),
        EntityRecordCreateRequest(
            entity_type_id=entity_type_record.entity_type_id, data={"identifier": machine_key}
        ),
    )
    if enroll:
        env["workflow_manager"].enroll_entity_for_actor(
            _actor(), machine_name=machine_key, entity_id=record.entity_id
        )
    return record.entity_id


def _runs(env, entity_id: str, *, kind: str | None = None) -> list[dict[str, Any]]:
    """Action-run rows for one entity, oldest first, optionally filtered by kind."""
    engine = env["db"].postgres_db_service().engine
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT action_kind, status, idempotency_key, scheduled_at, config_json "
                f"FROM {ACTION_RUNS_TABLE} WHERE entity_id = :entity_id "
                "ORDER BY created_at ASC"
            ),
            {"entity_id": entity_id},
        ).mappings().all()
    result = [dict(row) for row in rows]
    return [row for row in result if kind is None or row["action_kind"] == kind]


def _advance(env, entity_id: str):
    """Move APPLIED -> SCREENING, satisfying the required field."""
    return env["workflow_manager"].execute_transition_for_actor(
        _actor(),
        entity_id,
        TransitionExecuteRequest(
            entity_id=entity_id, trigger="advance", inputs={"approver": "mgr-1"}
        ),
    )


def _finish(env, entity_id: str):
    return env["workflow_manager"].execute_transition_for_actor(
        _actor(),
        entity_id,
        TransitionExecuteRequest(entity_id=entity_id, trigger="finish", inputs={}),
    )


def _complete_pending(env, entity_id: str) -> int:
    """Stand in for the worker finishing a run.

    The in-flight guard refuses a manual rerun while any run for that state is pending or
    running, so a rerun is only reachable once the automatic entry action has completed. No
    worker runs in the test suite, so the test has to close it out itself.
    """
    engine = env["db"].postgres_db_service().engine
    with engine.begin() as conn:
        return conn.execute(
            text(
                f"UPDATE {ACTION_RUNS_TABLE} SET status = 'succeeded' "
                "WHERE entity_id = :entity_id AND status IN ('pending', 'running')"
            ),
            {"entity_id": entity_id},
        ).rowcount


# ── the guard that makes the rest of this file meaningful ────────────────────


def test_canary_rows_are_really_written(sas_env):
    """`create_action_run` returns silently without a database, so prove we have one.

    Without this, a misconfigured fixture would make every test below pass while never writing
    a row.
    """
    assert sas_env["workflow_manager"].workflow_db.current_db is not None

    entity_id = _seed(sas_env, "sas_canary", "SasCanary")
    _advance(sas_env, entity_id)
    assert _runs(sas_env, entity_id), "no action_run row written; the rest of this file is void"


# ── arriving in a state ──────────────────────────────────────────────────────


def test_arriving_in_a_state_schedules_its_first_action(sas_env):
    """One pending row for the first action, carrying the config the worker needs."""
    entity_id = _seed(sas_env, "sas_entry", "SasEntry")
    _advance(sas_env, entity_id)

    rows = _runs(sas_env, entity_id)
    assert len(rows) == 1, "only the first action of the chain is scheduled up front"
    row = rows[0]
    assert row["action_kind"] == PRIMARY_KIND
    assert row["status"] == "pending"
    assert row["scheduled_at"] is None, "an entry action runs now, not on a timer"

    config = row["config_json"]
    assert config["agent_slug"] == "screener", "the action's own config is carried through"
    assert config["outcome_triggers"] == {"passed": "advance"}
    assert config["failure_policy"] == {"on_error": "halt"}
    assert config["origin_state"] == "SCREENING"
    assert config["state_action_index"] == 0
    assert config["state_action_total"] == 2, "the whole chain is counted, not just this action"
    assert config["isolated_rerun"] is False
    assert config["chain_id"], "the chain needs an id for the worker to follow it"


def test_the_entry_action_key_identifies_one_arrival(sas_env):
    """The key pins entity, state, transition and state version, so a replay cannot double-run."""
    entity_id = _seed(sas_env, "sas_key", "SasKey")
    _advance(sas_env, entity_id)

    key = _runs(sas_env, entity_id)[0]["idempotency_key"]
    version = _runs(sas_env, entity_id)[0]["config_json"]["origin_state_version"]
    assert key == f"{entity_id}:SCREENING:advance:v{version}:a0"


def test_scheduling_the_same_arrival_twice_creates_one_row(sas_env):
    """Re-running the entry step for an arrival already scheduled must not duplicate it.

    Two things independently prevent a duplicate: the pre-check that looks the key up, and the
    unique constraint on `idempotency_key`. Both are asserted, because a row count alone cannot
    tell them apart — with the pre-check gone the insert still fails on the constraint, and the
    surrounding `except` swallows it, so the row count looks identical either way.
    """
    entity_id = _seed(sas_env, "sas_dup", "SasDup")
    _advance(sas_env, entity_id)
    before = _runs(sas_env, entity_id)

    manager = sas_env["workflow_manager"]
    machine = manager.workflow_db.get_active_state_machine(
        organization_id=ORG, machine_name=sas_env["machine_key"]
    )

    attempts: list[str] = []
    original = manager.workflow_db.create_action_run

    def counting(**kwargs):
        attempts.append(kwargs["idempotency_key"])
        return original(**kwargs)

    manager.workflow_db.create_action_run = counting
    try:
        manager.state_action_scheduling.create_entry_action(
            ORG,
            entity_id,
            "SCREENING",
            machine.definition,
            "advance",
            before[0]["config_json"]["origin_state_version"],
        )
    finally:
        manager.workflow_db.create_action_run = original

    assert attempts == [], "an already-scheduled arrival must not even attempt an insert"
    assert len(_runs(sas_env, entity_id)) == len(before) == 1


def test_a_state_without_actions_schedules_nothing(sas_env):
    entity_id = _seed(sas_env, "sas_noact", "SasNoAct", actions_on_screening=False)
    _advance(sas_env, entity_id)
    assert _runs(sas_env, entity_id) == []


def test_enrolling_into_a_state_with_actions_schedules_them(sas_env):
    """Enrollment is the second way to arrive somewhere, and it schedules too.

    An entity enrolled into a workflow whose *initial* state carries actions gets one scheduled
    immediately, without any transition happening.
    """
    entity_id = _seed(
        sas_env, "sas_enrol", "SasEnrol", enroll=False, actions_on_initial=True
    )
    assert _runs(sas_env, entity_id) == [], "nothing is scheduled before enrollment"

    sas_env["workflow_manager"].enroll_entity_for_actor(
        _actor(), machine_name=sas_env["machine_key"], entity_id=entity_id
    )

    rows = _runs(sas_env, entity_id, kind=PRIMARY_KIND)
    assert len(rows) == 1
    assert rows[0]["config_json"]["origin_state"] == "APPLIED"


# ── SLA signals ──────────────────────────────────────────────────────────────


def test_a_state_with_an_sla_schedules_a_breach_signal(sas_env):
    """The signal is scheduled for the deadline, not for now."""
    entity_id = _seed(sas_env, "sas_sla", "SasSla", sla_on_screening=True)
    _advance(sas_env, entity_id)

    signals = _runs(sas_env, entity_id, kind="signal.fire")
    assert len(signals) == 1
    signal = signals[0]
    assert signal["status"] == "pending"
    assert signal["scheduled_at"] is not None, "an SLA signal fires later, so it needs a time"
    assert signal["idempotency_key"].startswith(f"sla:{entity_id}:SCREENING:")
    assert signal["config_json"]["signal_type"] == "sla_breach"
    assert signal["config_json"]["steps"], "the signal carries what to do when it fires"


def test_leaving_the_state_cancels_its_pending_sla_signal(sas_env):
    """The deadline only applies while the record is still there."""
    entity_id = _seed(sas_env, "sas_sla_cancel", "SasSlaCancel", sla_on_screening=True)
    _advance(sas_env, entity_id)
    assert [row["status"] for row in _runs(sas_env, entity_id, kind="signal.fire")] == ["pending"]

    _finish(sas_env, entity_id)

    assert [row["status"] for row in _runs(sas_env, entity_id, kind="signal.fire")] == ["cancelled"]


def test_a_state_without_an_sla_schedules_no_signal(sas_env):
    entity_id = _seed(sas_env, "sas_nosla", "SasNoSla")
    _advance(sas_env, entity_id)
    assert _runs(sas_env, entity_id, kind="signal.fire") == []


# ── tenancy of the dedup gate ────────────────────────────────────────────────


def test_the_dedup_gate_does_not_see_another_organizations_run(sas_env):
    """The idempotency pre-check is scoped to one organization.

    This query is the gate that decides whether a state action gets scheduled. Read across
    tenants it would answer a question about another organization's data, and the answer
    changes behaviour here — a "yes" silently skips scheduling.
    """
    entity_id = _seed(sas_env, "sas_tenancy", "SasTenancy")
    _advance(sas_env, entity_id)
    key = _runs(sas_env, entity_id)[0]["idempotency_key"]
    workflow_db = sas_env["workflow_manager"].workflow_db
    other_org = ENTITIES_TEST_ORG_IDS[1]
    assert other_org != ORG

    assert workflow_db.action_run_exists_by_idempotency_key(
        organization_id=ORG, idempotency_key=key
    ), "the owning organization must still find its own run"
    assert not workflow_db.action_run_exists_by_idempotency_key(
        organization_id=other_org, idempotency_key=key
    ), "another organization must not see this run"


# ── the deadline itself ──────────────────────────────────────────────────────

# `calculate_sla_due` is pure, and it runs on every single transition — the value it returns
# becomes the record's visible due date. These need no fixture.


def test_a_state_with_no_sla_has_no_deadline():
    """No SLA means no due date, rather than a due date equal to the arrival time."""
    assert StateActionSchedulingService.calculate_sla_due(datetime.now(UTC), None) is None


def test_the_deadline_is_the_arrival_plus_the_sla():
    arrived = datetime(2026, 9, 4, 10, 0, tzinfo=UTC)
    due = StateActionSchedulingService.calculate_sla_due(arrived, 3600)
    assert due == arrived + timedelta(hours=1)
    assert due.tzinfo is not None, "a naive deadline would compare wrongly against stored times"


def test_a_zero_sla_gives_a_deadline_on_arrival_rather_than_none():
    """Pins where the "no SLA" decision is made — not here.

    This function treats 0 as a real deadline that has already passed. It is
    `_state_sla_seconds` that discards non-positive values, so nothing reaches here with 0
    today. Pinned because the two would silently disagree if that filter were relaxed.
    """
    arrived = datetime(2026, 9, 4, 10, 0, tzinfo=UTC)
    assert StateActionSchedulingService.calculate_sla_due(arrived, 0) == arrived


# ── manual rerun ─────────────────────────────────────────────────────────────


def test_a_manual_rerun_schedules_a_fresh_isolated_run(sas_env):
    """A rerun is a new attempt, marked so the worker runs it alone rather than as a chain."""
    entity_id = _seed(sas_env, "sas_rerun", "SasRerun")
    _advance(sas_env, entity_id)
    _complete_pending(sas_env, entity_id)

    response = sas_env["workflow_manager"].rerun_state_action_for_actor(_actor(), entity_id, 0)

    assert response.state == "SCREENING"
    assert response.status == "pending"
    assert response.action_kinds == [PRIMARY_KIND]

    rerun = [
        row for row in _runs(sas_env, entity_id) if ":rerun:" in (row["idempotency_key"] or "")
    ]
    assert len(rerun) == 1
    config = rerun[0]["config_json"]
    assert rerun[0]["idempotency_key"] == f"{entity_id}:SCREENING:rerun:{response.run_id}"
    assert config["trigger_source"] == "manual_rerun"
    assert config["triggered_by"] == "user-sas-test", "who asked for it is recorded"
    assert config["isolated_rerun"] is True


def test_a_rerun_is_refused_while_one_is_already_pending(sas_env):
    """Two runs of the same state's action must not overlap."""
    entity_id = _seed(sas_env, "sas_inflight", "SasInFlight")
    _advance(sas_env, entity_id)

    with pytest.raises(ConflictError, match="already pending or running"):
        sas_env["workflow_manager"].rerun_state_action_for_actor(_actor(), entity_id, 0)


def test_a_rerun_is_refused_when_the_state_has_no_action(sas_env):
    entity_id = _seed(sas_env, "sas_rr_noact", "SasRrNoAct", actions_on_screening=False)
    _advance(sas_env, entity_id)

    with pytest.raises(ValidationError, match="has no action configured to re-run"):
        sas_env["workflow_manager"].rerun_state_action_for_actor(_actor(), entity_id, 0)


def test_a_rerun_is_refused_for_an_entity_with_no_workflow_state(sas_env):
    with pytest.raises(NotFoundError, match="workflow state was not found"):
        sas_env["workflow_manager"].rerun_state_action_for_actor(
            _actor(), "sas-entity-that-does-not-exist", 0
        )


# ── failure handling ─────────────────────────────────────────────────────────


def test_a_transition_still_succeeds_when_scheduling_fails(sas_env):
    """Scheduling is deliberately non-fatal, and this pins why.

    The state change is committed before the action is scheduled. Raising here would report
    failure for a record that has already moved, and would skip the "succeeded" audit row. So
    the failure is swallowed and logged, and the caller is told the transition worked — which is
    true. The cost is that a broken scheduler is invisible in the response, which is exactly how
    it once went unnoticed for a release; the log is the only signal.
    """
    entity_id = _seed(sas_env, "sas_fail", "SasFail")
    manager = sas_env["workflow_manager"]
    original = manager.workflow_db.create_action_run

    def raising(**_kwargs):
        raise RuntimeError("simulated action_run write failure")

    manager.workflow_db.create_action_run = raising
    try:
        response = _advance(sas_env, entity_id)
    finally:
        manager.workflow_db.create_action_run = original

    assert response.to_state == "SCREENING", "the transition itself still succeeded"
    assert _runs(sas_env, entity_id) == [], "and nothing was scheduled"


# ── handing the run to the worker ────────────────────────────────────────────


def test_the_row_is_committed_before_the_worker_is_told(sas_env):
    """Ordering matters: the worker must never be woken for a row it cannot read.

    The enqueue callback runs in-process, so if it fired before the commit, a worker on another
    connection could look the run up and find nothing. This asserts the row is already visible
    from a separate connection at the moment the callback fires.
    """
    entity_id = _seed(sas_env, "sas_order", "SasOrder")
    manager = sas_env["workflow_manager"]
    engine = sas_env["db"].postgres_db_service().engine
    visible_at_enqueue: list[bool] = []

    def enqueue(run_id: str) -> None:
        with engine.connect() as conn:
            found = conn.execute(
                text(f"SELECT 1 FROM {ACTION_RUNS_TABLE} WHERE run_id = :run_id"),
                {"run_id": run_id},
            ).fetchone()
        visible_at_enqueue.append(found is not None)

    manager.workflow_db.action_runs_enqueue_fn = enqueue
    try:
        _advance(sas_env, entity_id)
    finally:
        manager.workflow_db.action_runs_enqueue_fn = None

    assert visible_at_enqueue == [True], (
        "the run was not committed before the worker was told about it"
    )


def test_a_failed_handoff_leaves_the_run_pending_for_recovery(sas_env):
    """If waking the worker fails, the instruction must survive.

    Redis being unavailable is not a reason to lose the action. The row stays `pending` so a
    sweep can pick it up, and the transition is unaffected.
    """
    entity_id = _seed(sas_env, "sas_enqfail", "SasEnqFail")
    manager = sas_env["workflow_manager"]

    def failing_enqueue(_run_id: str) -> None:
        raise RuntimeError("simulated queue outage")

    manager.workflow_db.action_runs_enqueue_fn = failing_enqueue
    try:
        response = _advance(sas_env, entity_id)
    finally:
        manager.workflow_db.action_runs_enqueue_fn = None

    assert response.to_state == "SCREENING", "a queue outage must not fail the transition"
    rows = _runs(sas_env, entity_id, kind=PRIMARY_KIND)
    assert len(rows) == 1
    assert rows[0]["status"] == "pending", "the instruction must survive for reconciliation"


def test_a_failing_sla_signal_does_not_fail_the_transition(sas_env):
    """The two scheduling steps are independent, and neither can fail a committed transition.

    This used to raise. The record had already moved, so the caller was told the transition
    failed when it had not, and the succeeded audit event — written after this point — never
    happened, leaving the move with no audit trail. Both steps are now stepped over and logged.
    """
    entity_id = _seed(sas_env, "sas_partial", "SasPartial", sla_on_screening=True)
    manager = sas_env["workflow_manager"]
    scheduler = manager.state_action_scheduling
    original = scheduler._replace_sla_signal

    def raising(**_kwargs):
        raise RuntimeError("simulated SLA scheduling failure")

    scheduler._replace_sla_signal = raising
    try:
        response = _advance(sas_env, entity_id)
    finally:
        scheduler._replace_sla_signal = original

    assert response.to_state == "SCREENING", "a scheduling failure must not fail the transition"
    assert len(_runs(sas_env, entity_id, kind=PRIMARY_KIND)) == 1, (
        "the entry action was already scheduled and must be kept"
    )
    assert _runs(sas_env, entity_id, kind="signal.fire") == [], "the SLA step did fail"

    engine = sas_env["db"].postgres_db_service().engine
    with engine.connect() as conn:
        events = conn.execute(
            text(
                f"SELECT event_type FROM {AUDIT_EVENTS_TABLE} "
                "WHERE entity_id = :entity_id AND metadata_type = 'transition'"
            ),
            {"entity_id": entity_id},
        ).fetchall()
    assert [row[0] for row in events] == ["TRANSITION_SUCCEEDED"], (
        "the move must still be recorded in the audit trail"
    )
