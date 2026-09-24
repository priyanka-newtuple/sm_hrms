"""Tests for audit.entity_events and audit.transition_attempts.

Both tables are written by the workflow engine, not by users. These tests
exercise the manager directly — no public HTTP surface yet.
"""

from __future__ import annotations

import pytest

from exceptions import AuthorizationError, NotFoundError
from entities.db_models import EntitiesModelService
from entities.manager import EntitiesServiceManager
from entities.models.request import EntityRecordCreateRequest, EntityTypeCreateRequest


class _AlwaysAllowAuth:
    class _Decision:
        allowed = True
        reason = ""

    def check_access(self, _payload: dict[str, object]) -> "_AlwaysAllowAuth._Decision":
        return self._Decision()


class _DenyAuth:
    class _Decision:
        allowed = False
        reason = "denied"

    def check_access(self, _payload: dict[str, object]) -> "_DenyAuth._Decision":
        return self._Decision()


@pytest.fixture
def manager(entities_db_service_manager, clean_entities_tables) -> EntitiesServiceManager:
    db_service = EntitiesModelService(database_service_manager=entities_db_service_manager)
    mgr = EntitiesServiceManager(
        db_service,
        database_service_manager=entities_db_service_manager,
        config=None,
        auth_service_manager=_AlwaysAllowAuth(),
    )
    mgr.start()
    return mgr


def _admin_actor(org: str = "test-org-1") -> dict[str, object]:
    return {"user_id": "admin-user", "organization_id": org, "roles": ["admin"]}


def _seed_entity(manager: EntitiesServiceManager, org: str = "test-org-1") -> str:
    et = manager.create_entity_type_for_actor(
        _admin_actor(org),
        EntityTypeCreateRequest(name="Candidate", schema_definition={"fields": []}),
    )
    record = manager.create_entity_record_for_actor(
        _admin_actor(org),
        EntityRecordCreateRequest(
            entity_type_id=et.entity_type_id, data={"email": "alice@example.com"}
        ),
    )
    return record.entity_id


# ── audit.entity_events ─────────────────────────────────────────────────────


def test_emit_entity_event_creates_row(manager) -> None:
    entity_id = _seed_entity(manager)

    event = manager._emit_entity_event(
        organization_id="test-org-1",
        entity_id=entity_id,
        event_type="entity.created",
        actor_type="HUMAN",
        actor_id="admin-user",
        payload={"source": "rest"},
    )
    assert event.event_id
    assert event.event_type == "entity.created"
    assert event.payload == {"source": "rest"}
    assert event.occurred_at is not None


def test_emit_entity_event_idempotent_on_key(manager) -> None:
    entity_id = _seed_entity(manager)
    args = dict(
        organization_id="test-org-1",
        entity_id=entity_id,
        event_type="application.transitioned",
        actor_type="SYSTEM",
        idempotency_key="trans-001",
        payload={"from": "APPLIED", "to": "SCREENING"},
    )

    first = manager._emit_entity_event(**args)
    second = manager._emit_entity_event(**args)
    assert first.event_id == second.event_id  # same row returned

    listing = manager.list_entity_events_for_actor(_admin_actor(), entity_id)
    assert len(listing.items) == 1


def test_list_entity_events_returns_chronologically(manager) -> None:
    entity_id = _seed_entity(manager)
    for i, et in enumerate(["entity.created", "application.transitioned", "offer.approved"]):
        manager._emit_entity_event(
            organization_id="test-org-1",
            entity_id=entity_id,
            event_type=et,
            actor_type="SYSTEM",
            idempotency_key=f"k-{i}",
        )

    listing = manager.list_entity_events_for_actor(_admin_actor(), entity_id)
    assert [item.event_type for item in listing.items] == [
        "entity.created",
        "application.transitioned",
        "offer.approved",
    ]


def test_list_entity_events_filter_by_type(manager) -> None:
    entity_id = _seed_entity(manager)
    manager._emit_entity_event(
        organization_id="test-org-1",
        entity_id=entity_id,
        event_type="entity.created",
        actor_type="SYSTEM",
        idempotency_key="k1",
    )
    manager._emit_entity_event(
        organization_id="test-org-1",
        entity_id=entity_id,
        event_type="application.transitioned",
        actor_type="SYSTEM",
        idempotency_key="k2",
    )

    only_transitions = manager.list_entity_events_for_actor(
        _admin_actor(), entity_id, event_type="application.transitioned"
    )
    assert len(only_transitions.items) == 1
    assert only_transitions.items[0].event_type == "application.transitioned"


def test_list_entity_events_isolated_across_orgs(manager) -> None:
    entity_id = _seed_entity(manager)
    manager._emit_entity_event(
        organization_id="test-org-1",
        entity_id=entity_id,
        event_type="entity.created",
        actor_type="SYSTEM",
    )

    listing = manager.list_entity_events_for_actor(_admin_actor("test-org-2"), entity_id)
    assert listing.items == []


def test_emit_entity_event_persists_jsonb_payload(manager) -> None:
    """Sanity that JSONB round-trips a non-trivial payload (nested dict, list)."""
    entity_id = _seed_entity(manager)
    payload = {"nested": {"a": 1, "b": [1, 2, 3]}, "tag": "screening"}
    manager._emit_entity_event(
        organization_id="test-org-1",
        entity_id=entity_id,
        event_type="custom.event",
        actor_type="SYSTEM",
        idempotency_key="jsonb-1",
        payload=payload,
    )
    listing = manager.list_entity_events_for_actor(_admin_actor(), entity_id)
    assert listing.items[0].payload == payload


# ── audit.transition_attempts ───────────────────────────────────────────────


def test_record_transition_attempt_succeeded(manager) -> None:
    entity_id = _seed_entity(manager)

    attempt = manager._record_transition_attempt(
        organization_id="test-org-1",
        entity_id=entity_id,
        workflow_id="wf-ats",
        status="SUCCEEDED",
        from_state="APPLIED",
        to_state="SCREENING",
        trigger="advance",
        actor_id="admin-user",
        actor_role="admin",
        idempotency_key="ta-1",
        inputs={"foo": "bar"},
        guard_evaluations={"FIELD_PRESENT": True},
    )
    assert attempt.transition_attempt_id
    assert attempt.status == "SUCCEEDED"
    assert attempt.guard_evaluations == {"FIELD_PRESENT": True}


def test_record_transition_attempt_blocked(manager) -> None:
    entity_id = _seed_entity(manager)
    blocked = manager._record_transition_attempt(
        organization_id="test-org-1",
        entity_id=entity_id,
        workflow_id="wf-ats",
        status="BLOCKED",
        from_state="APPLIED",
        to_state="OFFER",
        failure_code="GUARD_FAILED",
        guard_evaluations={"HITL_REQUIRED": False},
    )
    assert blocked.status == "BLOCKED"
    assert blocked.failure_code == "GUARD_FAILED"


def test_record_transition_attempt_idempotent(manager) -> None:
    entity_id = _seed_entity(manager)
    args = dict(
        organization_id="test-org-1",
        entity_id=entity_id,
        workflow_id="wf-ats",
        status="SUCCEEDED",
        idempotency_key="ta-dup",
    )
    first = manager._record_transition_attempt(**args)
    second = manager._record_transition_attempt(**args)
    assert first.transition_attempt_id == second.transition_attempt_id


def test_list_transition_attempts_filter(manager) -> None:
    entity_id = _seed_entity(manager)
    for i, status in enumerate(["SUCCEEDED", "BLOCKED", "SUCCEEDED"]):
        manager._record_transition_attempt(
            organization_id="test-org-1",
            entity_id=entity_id,
            workflow_id="wf-ats",
            status=status,
            idempotency_key=f"ta-{i}",
        )

    blocked = manager.list_transition_attempts_for_actor(
        _admin_actor(), entity_id, status="BLOCKED"
    )
    assert len(blocked.items) == 1
    assert blocked.items[0].status == "BLOCKED"

    all_attempts = manager.list_transition_attempts_for_actor(_admin_actor(), entity_id)
    assert len(all_attempts.items) == 3


def test_list_transition_attempts_isolated_across_orgs(manager) -> None:
    entity_id = _seed_entity(manager)
    manager._record_transition_attempt(
        organization_id="test-org-1",
        entity_id=entity_id,
        workflow_id="wf-ats",
        status="SUCCEEDED",
    )
    listing = manager.list_transition_attempts_for_actor(
        _admin_actor("test-org-2"), entity_id
    )
    assert listing.items == []


def test_list_transition_attempts_denied_when_auth_fails(
    entities_db_service_manager, clean_entities_tables
) -> None:
    db_service = EntitiesModelService(database_service_manager=entities_db_service_manager)
    permissive = EntitiesServiceManager(
        db_service,
        database_service_manager=entities_db_service_manager,
        config=None,
        auth_service_manager=_AlwaysAllowAuth(),
    )
    permissive.start()
    et = permissive.create_entity_type_for_actor(
        _admin_actor(),
        EntityTypeCreateRequest(name="Candidate", schema_definition={"fields": []}),
    )
    record = permissive.create_entity_record_for_actor(
        _admin_actor(),
        EntityRecordCreateRequest(entity_type_id=et.entity_type_id, data={}),
    )

    deny = EntitiesServiceManager(
        db_service,
        database_service_manager=entities_db_service_manager,
        config=None,
        auth_service_manager=_DenyAuth(),
    )
    deny.start()
    with pytest.raises(AuthorizationError):
        deny.list_transition_attempts_for_actor(_admin_actor(), record.entity_id)
