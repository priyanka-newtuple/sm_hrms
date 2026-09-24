"""End-to-end behaviour of the `entity.assign_user` workflow action.

Every other test of this feature either checks that a run row was *scheduled*,
or calls the executor with a hand-built input. Neither shows what actually
happens when a record enters a state: whether the assignment lands, whether the
outcome routes the record onward, and when the failure policy takes over
instead. This file closes that gap.

It drives the real chain:

    publish workflow -> enrol entity -> state entry writes an action_runs row
        -> worker executes it -> assignee written -> outcome fires a transition

against real Postgres, with real workflow definitions, real `users` and
`user_organizations` rows, and the real audit trail. The single substitution is
the queue: rather than Redis and a background thread, `_drain` calls the
worker's own `_execute_action_run`, which is the same code the live worker runs
once it has popped an id. Delivery through Redis is therefore the one link not
covered here.

Roles are a permissive double so these tests describe assignment behaviour
rather than re-testing RBAC, which `test_entity_assignee_originator.py` covers.
"""

from __future__ import annotations

import os
import uuid
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
from background_jobs.db_models import BackgroundJobsModelService
from background_jobs.manager import BackgroundJobsServiceManager
from common.auth import build_system_actor
from entities.db_models import EntitiesModelService
from entities.manager import EntitiesServiceManager
from entities.models.request import EntityRecordCreateRequest, EntityTypeCreateRequest
from executor.manager import ExecutorServiceManager
from executor.models.interface import ENTITY_ASSIGN_USER_ACTION_KIND
from tests.conftest import ENTITIES_TEST_ORG_IDS
from user.db_models import UserModelService, UserStatus
from user.manager import UserServiceManager
from workflow.db_models import WorkflowModelService
from workflow.models.interface import (
    EntitySchema,
    State,
    StateAction,
    StateMachineDefinition,
    Transition,
)
from workflow.models.request import StateMachineCreateRequest, TransitionExecuteRequest

ORG = ENTITIES_TEST_ORG_IDS[0]
APP_SCHEMA = os.environ.get("POSTGRES_APP_SCHEMA", "modular_backend")
ACTION_RUNS = f"{APP_SCHEMA}.action_runs"
AUDIT_EVENTS = f"{APP_SCHEMA}_audit.audit_events"

INTAKE, REVIEW, TRIAGE, DONE = "Intake", "Review", "Triage", "Done"
TO_REVIEW, TO_DONE, TO_TRIAGE = "to_review", "to_done", "to_triage"


# ── workflow shape ───────────────────────────────────────────────────────────


def _assign_action(
    config: dict[str, Any],
    *,
    outcome_triggers: dict[str, str] | None = None,
    on_failure: str = "block",
) -> StateAction:
    return StateAction(
        kind=ENTITY_ASSIGN_USER_ACTION_KIND,
        config=config,
        outcome_triggers=outcome_triggers or {},
        failure_policy={"on_failure": on_failure},
    )


def _definition(
    machine_key: str,
    entity_type: str,
    *,
    review_action: StateAction | None,
    intake_action: StateAction | None = None,
) -> StateMachineDefinition:
    """Intake -> Review -> Done, with Triage as the refusal branch.

    Two outgoing transitions from Review so an outcome mapping has a real
    choice to make: routing to Done proves the happy path, Triage proves a
    refusal was routed rather than swallowed.
    """
    return StateMachineDefinition(
        machine_key=machine_key,
        name=machine_key,
        description="",
        entity_type=entity_type,
        entity_schema=EntitySchema(entity_type=entity_type, fields=[]),
        states=[
            State(
                name=INTAKE,
                tags=["initial"],
                order=1,
                on_state_actions=[intake_action] if intake_action else [],
            ),
            State(
                name=REVIEW,
                order=2,
                on_state_actions=[review_action] if review_action else [],
            ),
            State(name=TRIAGE, order=3),
            State(name=DONE, tags=["terminal"], order=4),
        ],
        initial_state=INTAKE,
        transitions=[
            Transition(key=TO_REVIEW, trigger=TO_REVIEW, label="To review",
                       from_state=INTAKE, to_state=REVIEW, required_fields=[], guards=[]),
            Transition(key=TO_DONE, trigger=TO_DONE, label="To done",
                       from_state=REVIEW, to_state=DONE, required_fields=[], guards=[]),
            Transition(key=TO_TRIAGE, trigger=TO_TRIAGE, label="To triage",
                       from_state=REVIEW, to_state=TRIAGE, required_fields=[], guards=[]),
        ],
    )


# ── environment ──────────────────────────────────────────────────────────────


@pytest.fixture
def env(entities_db_service_manager):
    """Workflow, entities and worker wired together the way `main.py` wires them."""
    db = entities_db_service_manager
    entities_db = EntitiesModelService(database_service_manager=db)
    audit_events = AuditEventsModelService(database_service_manager=db)
    user_manager = UserServiceManager(UserModelService(db))

    entities_manager = EntitiesServiceManager(
        entities_db,
        database_service_manager=db,
        config=None,
        roles_manager=AllowAllEntityRolesManager(),
        audit_service_manager=AuditServiceManager(audit_events),
        user_service_manager=user_manager,
    )
    entities_manager.start()

    workflow_manager = make_workflow_manager(
        WorkflowModelService(db),
        db,
        entities_service_manager=entities_manager,
        roles_manager=UnrestrictedRolesManager(),
        audit_events_service=audit_events,
    )
    workflow_manager.start()

    executor_manager = ExecutorServiceManager(
        _database_service_manager=db, _mail_service=object()
    )
    executor_manager.bind_assign_user_services(entities_manager, user_manager)

    worker = BackgroundJobsServiceManager(
        BackgroundJobsModelService(db),
        db,
        None,
        executor_service_manager=executor_manager,
    )
    worker.workflow_service_manager = workflow_manager

    return {
        "db": db,
        "entities": entities_manager,
        "workflow": workflow_manager,
        "worker": worker,
        "users": user_manager,
    }


@pytest.fixture
def seed_user(entities_db_service_manager):
    """Create org users, and remove them afterwards."""
    created: list[str] = []
    engine = entities_db_service_manager.postgres_db_service().engine

    def _make(full_name: str, *, membership: str = UserStatus.ACTIVE.value) -> str:
        user_id = str(uuid.uuid4())
        created.append(user_id)
        with engine.begin() as conn:
            conn.execute(
                text(
                    f'INSERT INTO "{APP_SCHEMA}".users '
                    "(id, email, full_name, role, status, auth_type) "
                    "VALUES (:id, :email, :name, 'recruiter', 'active', 'local')"
                ),
                {"id": user_id, "email": f"{user_id}@example.test", "name": full_name},
            )
            conn.execute(
                text(
                    f'INSERT INTO "{APP_SCHEMA}".user_organizations '
                    "(id, user_id, organization_id, role, status) "
                    "VALUES (:i, :u, :o, 'recruiter', :s)"
                ),
                {"i": str(uuid.uuid4()), "u": user_id, "o": ORG, "s": membership},
            )
        return user_id

    yield _make

    with engine.begin() as conn:
        conn.execute(
            text(f'DELETE FROM "{APP_SCHEMA}".user_organizations WHERE user_id = ANY(:i)'),
            {"i": created},
        )
        conn.execute(text(f'DELETE FROM "{APP_SCHEMA}".users WHERE id = ANY(:i)'), {"i": created})


# ── helpers ──────────────────────────────────────────────────────────────────


def _actor(user_id: str) -> dict[str, object]:
    return {"user_id": user_id, "organization_id": ORG, "actor_type": "user", "roles": ["admin"]}


def _publish(env, *, review_action, intake_action=None, creator: dict | None = None) -> str:
    """Publish a workflow, create one record, enrol it. Returns the entity id."""
    suffix = uuid.uuid4().hex[:8]
    machine_key, entity_type = f"assign_e2e_{suffix}", f"AssignE2E{suffix}"
    actor = creator or _actor("seed-user")
    entity_type_record = env["entities"].create_entity_type_for_actor(
        actor, EntityTypeCreateRequest(name=entity_type, schema_definition={"fields": []})
    )
    env["workflow"].workflow_db.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name=machine_key,
            version=1,
            is_active=True,
            definition=_definition(
                machine_key, entity_type,
                review_action=review_action, intake_action=intake_action,
            ),
        ),
        organization_id=ORG,
    )
    record = env["entities"].create_entity_record_for_actor(
        actor,
        EntityRecordCreateRequest(
            entity_type_id=entity_type_record.entity_type_id, data={"identifier": machine_key}
        ),
    )
    env["workflow"].enroll_entity_for_actor(
        actor, machine_name=machine_key, entity_id=record.entity_id
    )
    return record.entity_id


def _drain(env, entity_id: str, *, limit: int = 5) -> int:
    """Execute every pending run for this entity, as the worker would.

    Loops because an action can fire a transition whose destination schedules
    another action. `limit` stops a misconfigured cycle from hanging the suite.
    """
    executed = 0
    for _ in range(limit):
        pending = [r for r in _runs(env, entity_id) if r["status"] == "pending"]
        if not pending:
            break
        for run in pending:
            env["worker"]._execute_action_run(
                run_id=run["run_id"],
                organization_id=ORG,
                entity_id=entity_id,
                action_kind=run["action_kind"],
                config_json=run["config_json"],
            )
            executed += 1
    return executed


def _runs(env, entity_id: str) -> list[dict[str, Any]]:
    engine = env["db"].postgres_db_service().engine
    with engine.connect() as conn:
        return [
            dict(r)
            for r in conn.execute(
                text(
                    f"SELECT run_id, action_kind, status, outcome, config_json "
                    f"FROM {ACTION_RUNS} WHERE entity_id = :e ORDER BY created_at"
                ),
                {"e": entity_id},
            ).mappings()
        ]


def _state(env, entity_id: str) -> str:
    return env["workflow"]._hydrate_entity_state(ORG, entity_id).current_state


def _assignee(env, entity_id: str) -> str | None:
    return env["entities"].get_entity_record(organization_id=ORG, entity_id=entity_id).assignee_id


def _events(env, entity_id: str, event_type: str) -> list[dict[str, Any]]:
    engine = env["db"].postgres_db_service().engine
    with engine.connect() as conn:
        return [
            dict(r)
            for r in conn.execute(
                text(
                    f"SELECT actor_type, actor_id, metadata FROM {AUDIT_EVENTS} "
                    f"WHERE entity_id = :e AND event_type = :t ORDER BY event_timestamp, id"
                ),
                {"e": entity_id, "t": event_type},
            ).mappings()
        ]


# ── 1. the happy path ────────────────────────────────────────────────────────


def test_a_chosen_user_is_assigned_and_the_record_moves_on(env, seed_user, clean_entities_tables):
    """Assigning succeeds, and the `assigned` mapping advances the record."""
    target = seed_user("Mohit Rana")
    entity_id = _publish(
        env,
        review_action=_assign_action(
            {"assignment_type": "user", "user_id": target},
            outcome_triggers={"assigned": TO_DONE},
        ),
    )
    env["workflow"].execute_transition_for_actor(
        _actor("nisha"), entity_id,
        TransitionExecuteRequest(entity_id=entity_id, trigger=TO_REVIEW),
    )
    _drain(env, entity_id)

    assert _assignee(env, entity_id) == target
    assert _state(env, entity_id) == DONE
    assert [r["outcome"] for r in _runs(env, entity_id)] == ["assigned"]
    assert [r["status"] for r in _runs(env, entity_id)] == ["succeeded"]


def test_the_action_records_itself_as_a_workflow_action_by_the_system(
    env, seed_user, clean_entities_tables
):
    """History must show the worker did this, not the person who transitioned."""
    target = seed_user("Mohit Rana")
    entity_id = _publish(
        env, review_action=_assign_action({"assignment_type": "user", "user_id": target})
    )
    env["workflow"].execute_transition_for_actor(
        _actor("nisha"), entity_id,
        TransitionExecuteRequest(entity_id=entity_id, trigger=TO_REVIEW),
    )
    _drain(env, entity_id)

    changed = _events(env, entity_id, "ENTITY_ASSIGNEE_CHANGED")
    assert len(changed) == 1
    assert changed[0]["actor_type"] == "system"
    assert changed[0]["actor_id"] is None
    assert changed[0]["metadata"]["assignment_source"] == "workflow_action"
    assert changed[0]["metadata"]["new_assignee_id"] == target
    assert changed[0]["metadata"]["action_run_id"]


# ── 2. an action that runs on enrolment ──────────────────────────────────────


def test_the_action_fires_on_enrolment_not_only_on_a_transition(
    env, seed_user, clean_entities_tables
):
    """Arriving in the initial state counts as arriving."""
    target = seed_user("Mohit Rana")
    entity_id = _publish(
        env,
        review_action=None,
        intake_action=_assign_action({"assignment_type": "user", "user_id": target}),
    )
    _drain(env, entity_id)

    assert _assignee(env, entity_id) == target
    assert _state(env, entity_id) == INTAKE


# ── 3. refusals route, which is the behaviour the fix introduced ─────────────


def test_a_suspended_user_routes_to_the_mapped_state_without_assigning(
    env, seed_user, clean_entities_tables
):
    """The refusal is an answer the author can route on, not a breakage."""
    target = seed_user("Mohit Rana", membership=UserStatus.SUSPENDED.value)
    entity_id = _publish(
        env,
        review_action=_assign_action(
            {"assignment_type": "user", "user_id": target},
            outcome_triggers={"assigned": TO_DONE, "user_suspended": TO_TRIAGE},
        ),
    )
    env["workflow"].execute_transition_for_actor(
        _actor("nisha"), entity_id,
        TransitionExecuteRequest(entity_id=entity_id, trigger=TO_REVIEW),
    )
    _drain(env, entity_id)

    assert _assignee(env, entity_id) is None
    assert _state(env, entity_id) == TRIAGE
    assert _runs(env, entity_id)[0]["outcome"] == "user_suspended"


def test_an_unmapped_refusal_stays_put_without_failing_the_run(
    env, seed_user, clean_entities_tables
):
    """Not mapping an outcome is allowed, and must not fail the run.

    This is the ordinary configuration: the author maps `assigned` and leaves
    the four refusals alone. The action still did its job — it declined to
    assign a suspended user — so the run succeeds, the record stays where it
    is, and the outcome is recorded for the activity log to show.
    """
    target = seed_user("Mohit Rana", membership=UserStatus.SUSPENDED.value)
    entity_id = _publish(
        env,
        review_action=_assign_action(
            {"assignment_type": "user", "user_id": target},
            outcome_triggers={"assigned": TO_DONE},
        ),
    )
    env["workflow"].execute_transition_for_actor(
        _actor("nisha"), entity_id,
        TransitionExecuteRequest(entity_id=entity_id, trigger=TO_REVIEW),
    )
    _drain(env, entity_id)

    assert _assignee(env, entity_id) is None
    assert _state(env, entity_id) == REVIEW
    assert _runs(env, entity_id)[0]["status"] == "succeeded"
    assert _runs(env, entity_id)[0]["outcome"] == "user_suspended"


def test_the_activity_log_says_why_the_action_did_not_assign(
    env, seed_user, clean_entities_tables
):
    """A completed run must carry the reason, or the timeline cannot show one.

    Without the reason on the event, every outcome renders as a bare "Action
    completed" and a refusal is indistinguishable from a successful assign.
    """
    target = seed_user("Mohit Rana", membership=UserStatus.SUSPENDED.value)
    entity_id = _publish(
        env,
        review_action=_assign_action(
            {"assignment_type": "user", "user_id": target},
            outcome_triggers={"assigned": TO_DONE},
        ),
    )
    env["workflow"].execute_transition_for_actor(
        _actor("nisha"), entity_id,
        TransitionExecuteRequest(entity_id=entity_id, trigger=TO_REVIEW),
    )
    _drain(env, entity_id)

    completed = _events(env, entity_id, "ACTION_COMPLETED")
    assert completed[0]["metadata"]["message"] == "User is suspended."
    assert completed[0]["metadata"]["outcome"] == "user_suspended"
    # Drawn in the failure style, because a green tick reads the same as an
    # assignment that worked.
    assert completed[0]["metadata"]["refused"] is True
    # ...but only the drawing changes. Fail the run and outcome routing dies,
    # since triggers resolve for successful responses only.
    assert _runs(env, entity_id)[0]["status"] == "succeeded"


# ── 4. originator mode ───────────────────────────────────────────────────────


def test_originator_mode_assigns_the_creator_not_the_caller(
    env, seed_user, clean_entities_tables
):
    creator = seed_user("Virat Kohli")
    entity_id = _publish(
        env,
        review_action=_assign_action(
            {"assignment_type": "originator"}, outcome_triggers={"assigned": TO_DONE}
        ),
        creator=_actor(creator),
    )
    env["workflow"].execute_transition_for_actor(
        _actor("nisha"), entity_id,
        TransitionExecuteRequest(entity_id=entity_id, trigger=TO_REVIEW),
    )
    _drain(env, entity_id)

    assert _assignee(env, entity_id) == creator
    assert _state(env, entity_id) == DONE


def test_a_system_created_record_has_no_originator_to_assign(env, clean_entities_tables):
    """A scheduler-created record carries no human actor, so nothing is written."""
    entity_id = _publish(
        env,
        review_action=_assign_action(
            {"assignment_type": "originator"},
            outcome_triggers={"assigned": TO_DONE, "originator_not_found": TO_TRIAGE},
        ),
        creator=build_system_actor(ORG, source="scheduler"),
    )
    env["workflow"].execute_transition_for_actor(
        _actor("nisha"), entity_id,
        TransitionExecuteRequest(entity_id=entity_id, trigger=TO_REVIEW),
    )
    _drain(env, entity_id)

    assert _assignee(env, entity_id) is None
    assert _runs(env, entity_id)[0]["outcome"] == "originator_not_found"
    assert _state(env, entity_id) == TRIAGE
    # The originator path is a separate branch from the configured-user one, so
    # prove it is drawn as "made no change" too — and that routing still works
    # while it is (the record reached Triage above).
    assert _events(env, entity_id, "ACTION_COMPLETED")[0]["metadata"]["refused"] is True


# ── 5. running the same action twice ─────────────────────────────────────────


def test_reassigning_the_current_holder_writes_no_second_history_row(
    env, seed_user, clean_entities_tables
):
    """A retried run must not look like fresh work."""
    target = seed_user("Mohit Rana")
    entity_id = _publish(
        env,
        review_action=None,
        intake_action=_assign_action({"assignment_type": "user", "user_id": target}),
    )
    _drain(env, entity_id)
    first = _runs(env, entity_id)[0]

    env["worker"]._execute_action_run(
        run_id=first["run_id"], organization_id=ORG, entity_id=entity_id,
        action_kind=first["action_kind"], config_json=first["config_json"],
    )

    assert _assignee(env, entity_id) == target
    assert len(_events(env, entity_id, "ENTITY_ASSIGNEE_CHANGED")) == 1


# ── 6. genuine failure still obeys the failure policy ────────────────────────


def test_a_broken_action_is_blocked_by_the_failure_policy(env, clean_entities_tables):
    """`failed` is not routable: On failure governs it, and Block freezes the record."""
    entity_id = _publish(
        env,
        review_action=_assign_action(
            {"assignment_type": "user"},  # no user_id — config the worker cannot act on
            outcome_triggers={"assigned": TO_DONE, "failed": TO_TRIAGE},
            on_failure="block",
        ),
    )
    env["workflow"].execute_transition_for_actor(
        _actor("nisha"), entity_id,
        TransitionExecuteRequest(entity_id=entity_id, trigger=TO_REVIEW),
    )
    _drain(env, entity_id)

    assert _assignee(env, entity_id) is None
    assert _runs(env, entity_id)[0]["status"] == "failed"
    assert _state(env, entity_id) == REVIEW
