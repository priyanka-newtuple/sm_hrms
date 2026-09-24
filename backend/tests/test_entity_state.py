"""Tests for runtime.entity_state — internal write + actor-gated reads.

No HTTP surface yet; entity_state is written by the workflow engine, not
by users. These tests exercise the manager directly.
"""

from __future__ import annotations

import pytest

from exceptions import AuthorizationError, ConflictError, NotFoundError, ValidationError
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
            entity_type_id=et.entity_type_id,
            data={"email": "alice@example.com"},
        ),
    )
    return record.entity_id


def test_enroll_entity_creates_state_row(manager) -> None:
    entity_id = _seed_entity(manager)

    state = manager._enroll_entity(
        organization_id="test-org-1",
        entity_id=entity_id,
        workflow_id="wf-1",
        current_state="APPLIED",
    )
    assert state.state_id
    assert state.entity_id == entity_id
    assert state.workflow_id == "wf-1"
    assert state.current_state == "APPLIED"
    assert state.state_version == 0
    assert state.state_entered_at is not None


def test_enroll_entity_supports_multiple_workflows(manager) -> None:
    """The structural unlock: one entity, many workflows."""
    entity_id = _seed_entity(manager)

    s1 = manager._enroll_entity(
        organization_id="test-org-1",
        entity_id=entity_id,
        workflow_id="wf-ats",
        current_state="APPLIED",
    )
    s2 = manager._enroll_entity(
        organization_id="test-org-1",
        entity_id=entity_id,
        workflow_id="wf-referral",
        current_state="REFERRED",
    )
    assert s1.state_id != s2.state_id
    assert s1.workflow_id != s2.workflow_id

    listing = manager.list_entity_states_for_actor(_admin_actor(), entity_id)
    assert listing.organization_id == "test-org-1"
    assert listing.entity_id == entity_id
    assert {item.workflow_id for item in listing.items} == {"wf-ats", "wf-referral"}


def test_enroll_entity_duplicate_workflow_raises_conflict(manager) -> None:
    entity_id = _seed_entity(manager)

    manager._enroll_entity(
        organization_id="test-org-1",
        entity_id=entity_id,
        workflow_id="wf-1",
        current_state="APPLIED",
    )
    with pytest.raises(ConflictError):
        manager._enroll_entity(
            organization_id="test-org-1",
            entity_id=entity_id,
            workflow_id="wf-1",
            current_state="APPLIED",
        )


def test_get_entity_state_for_actor_returns_row(manager) -> None:
    entity_id = _seed_entity(manager)
    enrolled = manager._enroll_entity(
        organization_id="test-org-1",
        entity_id=entity_id,
        workflow_id="wf-1",
        current_state="APPLIED",
    )

    fetched = manager.get_entity_state_for_actor(_admin_actor(), enrolled.state_id)
    assert fetched.state_id == enrolled.state_id
    assert fetched.current_state == "APPLIED"


def test_get_entity_state_isolated_across_orgs(manager) -> None:
    entity_id = _seed_entity(manager)
    enrolled = manager._enroll_entity(
        organization_id="test-org-1",
        entity_id=entity_id,
        workflow_id="wf-1",
        current_state="APPLIED",
    )

    with pytest.raises(NotFoundError):
        manager.get_entity_state_for_actor(_admin_actor("test-org-2"), enrolled.state_id)


def test_list_entity_states_filter_by_workflow(manager) -> None:
    entity_id = _seed_entity(manager)
    manager._enroll_entity(
        organization_id="test-org-1",
        entity_id=entity_id,
        workflow_id="wf-a",
        current_state="APPLIED",
    )
    manager._enroll_entity(
        organization_id="test-org-1",
        entity_id=entity_id,
        workflow_id="wf-b",
        current_state="APPLIED",
    )

    only_a = manager.list_entity_states_for_actor(
        _admin_actor(), entity_id, workflow_id="wf-a"
    )
    assert len(only_a.items) == 1
    assert only_a.items[0].workflow_id == "wf-a"


def test_list_entity_states_scoped_by_actor_org(manager) -> None:
    entity_id = _seed_entity(manager)
    manager._enroll_entity(
        organization_id="test-org-1",
        entity_id=entity_id,
        workflow_id="wf-1",
        current_state="APPLIED",
    )

    listing = manager.list_entity_states_for_actor(_admin_actor("test-org-2"), entity_id)
    assert listing.items == []


def test_list_entity_states_denied_when_auth_fails(entities_db_service_manager, clean_entities_tables) -> None:
    db_service = EntitiesModelService(database_service_manager=entities_db_service_manager)
    mgr = EntitiesServiceManager(
        db_service,
        database_service_manager=entities_db_service_manager,
        config=None,
        auth_service_manager=_DenyAuth(),
    )
    mgr.start()

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

    with pytest.raises(AuthorizationError):
        mgr.list_entity_states_for_actor(_admin_actor(), record.entity_id)
