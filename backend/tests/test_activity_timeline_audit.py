"""Tests for the Activity Timeline Audit feature.

Covers:
- Write side: 5 CRUD operations emit the correct audit events
- Actor identity: name and role snapshotted at write time
- Read API: list_entity_events_for_actor — pagination, filtering, auth, sort order
- Field masking: three-state model on ENTITY_UPDATED payloads
- HTTP endpoint: GET /entity-records/{entity_id}/events
"""

from __future__ import annotations

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from common.auth import build_system_actor
from entities.controller import EntitiesRestController
from entities.db_models import EntitiesModelService
from entities.manager import EntitiesServiceManager
from entities.models.interface import (
    EntityArchivedPayload,
    EntityAssigneeChangedPayload,
    EntityAuditEventType,
    EntityCreatedPayload,
    EntityUpdatedPayload,
)
from entities.models.request import (
    EntityRecordCreateRequest,
    EntityRecordUpdateRequest,
    EntityTypeCreateRequest,
)
from exceptions import AuthorizationError, NotFoundError
from user.db_models import UserModelService
from user.manager import UserServiceManager


# ── Auth stubs ────────────────────────────────────────────────────────────────


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


# ── Roles manager stubs ───────────────────────────────────────────────────────


class _AllVisibleRolesManager:
    """Allows everything — no field restrictions."""

    def check_entity_permission(
        self, db: object, user_id: str, org_id: str, entity_type: str, action: str
    ) -> bool:
        return True

    def get_visible_fields(
        self, db: object, user_id: str, org_id: str, entity_type: str
    ) -> list[str] | None:
        return None  # system bypass — all fields visible

    def get_masked_fields(
        self, db: object, user_id: str, org_id: str, entity_type: str
    ) -> list[str]:
        return []

    def get_editable_fields(
        self, db: object, user_id: str, org_id: str, entity_type: str
    ) -> list[str] | None:
        return None  # all fields editable


class _RestrictedRolesManager:
    """Simulates a role where some fields are masked or hidden entirely."""

    def __init__(self, visible: list[str], masked: list[str]) -> None:
        self._visible = visible
        self._masked = masked

    def check_entity_permission(
        self, db: object, user_id: str, org_id: str, entity_type: str, action: str
    ) -> bool:
        return True

    def get_visible_fields(
        self, db: object, user_id: str, org_id: str, entity_type: str
    ) -> list[str] | None:
        return self._visible

    def get_masked_fields(
        self, db: object, user_id: str, org_id: str, entity_type: str
    ) -> list[str]:
        return self._masked

    def get_editable_fields(
        self, db: object, user_id: str, org_id: str, entity_type: str
    ) -> list[str] | None:
        return None  # all fields editable


class _DenyEntityPermissionRolesManager:
    """Denies entity-type view permission — used to test 403 on read."""

    def check_entity_permission(
        self, db: object, user_id: str, org_id: str, entity_type: str, action: str
    ) -> bool:
        return False

    def get_visible_fields(
        self, db: object, user_id: str, org_id: str, entity_type: str
    ) -> list[str] | None:
        return None

    def get_masked_fields(
        self, db: object, user_id: str, org_id: str, entity_type: str
    ) -> list[str]:
        return []

    def get_editable_fields(
        self, db: object, user_id: str, org_id: str, entity_type: str
    ) -> list[str] | None:
        return None


# ── Helpers ───────────────────────────────────────────────────────────────────

ORG = "test-org-1"
OTHER_ORG = "test-org-2"


def _actor(org: str = ORG, user_id: str = "user-audit-test") -> dict[str, object]:
    return {"user_id": user_id, "organization_id": org, "roles": ["admin"]}


def _build_manager(
    entities_db_service_manager: object,
    *,
    roles_manager: object | None = None,
    user_svc: UserServiceManager | None = None,
) -> EntitiesServiceManager:
    db_service = EntitiesModelService(database_service_manager=entities_db_service_manager)
    _user_svc = user_svc or UserServiceManager(
        UserModelService(entities_db_service_manager), entities_db_service_manager
    )
    mgr = EntitiesServiceManager(
        db_service,
        database_service_manager=entities_db_service_manager,
        config=None,
        auth_service_manager=_AlwaysAllowAuth(),
        roles_manager=roles_manager or _AllVisibleRolesManager(),
        user_service_manager=_user_svc,
    )
    mgr.start()
    return mgr


def _seed_entity_type(mgr: EntitiesServiceManager, org: str = ORG) -> str:
    et = mgr.create_entity_type_for_actor(
        _actor(org),
        EntityTypeCreateRequest(name="Candidate", schema_definition={"fields": []}),
    )
    return et.entity_type_id


def _seed_entity(mgr: EntitiesServiceManager, org: str = ORG) -> tuple[str, str]:
    """Return (entity_type_id, entity_id)."""
    et_id = _seed_entity_type(mgr, org)
    record = mgr.create_entity_record_for_actor(
        _actor(org),
        EntityRecordCreateRequest(
            entity_type_id=et_id,
            data={"identifier": "alice-001", "name": "Alice", "title": "Engineer", "salary": "100k"},
        ),
    )
    return et_id, record.entity_id


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mgr(entities_db_service_manager, clean_entities_tables) -> EntitiesServiceManager:
    return _build_manager(entities_db_service_manager)


@pytest.fixture
def client(entities_db_service_manager, clean_entities_tables) -> TestClient:
    manager = _build_manager(entities_db_service_manager)
    controller = EntitiesRestController(manager)
    router = APIRouter()
    controller.prepare(router)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


HEADERS = {"x-user-id": "user-audit-test", "x-org-id": ORG, "x-user-roles": "admin"}
OTHER_ORG_HEADERS = {"x-user-id": "other-user", "x-org-id": OTHER_ORG, "x-user-roles": "admin"}


# ── Write side: 5 CRUD operations emit correct events ─────────────────────────


def test_create_entity_record_emits_entity_created_event(mgr) -> None:
    et_id = _seed_entity_type(mgr)
    record = mgr.create_entity_record_for_actor(
        _actor(),
        EntityRecordCreateRequest(
            entity_type_id=et_id,
            data={"identifier": "bob-001", "name": "Bob"},
        ),
    )
    listing = mgr.list_entity_events_for_actor(_actor(), record.entity_id)
    assert listing.total == 1
    event = listing.items[0]
    assert event.event_type == EntityAuditEventType.CREATED
    assert event.entity_id == record.entity_id
    assert event.actor_type == "user"
    assert event.actor_id == "user-audit-test"


def test_create_entity_record_event_payload_contains_identifier(mgr) -> None:
    et_id = _seed_entity_type(mgr)
    record = mgr.create_entity_record_for_actor(
        _actor(),
        EntityRecordCreateRequest(entity_type_id=et_id, data={"identifier": "cand-001"}),
    )
    listing = mgr.list_entity_events_for_actor(_actor(), record.entity_id)
    assert isinstance(listing.items[0].payload, EntityCreatedPayload)
    assert listing.items[0].payload.identifier == "cand-001"


def test_update_entity_record_emits_entity_updated_with_changed_fields_only(mgr) -> None:
    _, entity_id = _seed_entity(mgr)
    mgr.update_entity_record_for_actor(
        _actor(),
        entity_id,
        EntityRecordUpdateRequest(data={"name": "Alice", "title": "Senior Engineer"}),
    )
    listing = mgr.list_entity_events_for_actor(_actor(), entity_id)
    update_events = [e for e in listing.items if e.event_type == EntityAuditEventType.UPDATED]
    assert len(update_events) == 1
    assert isinstance(update_events[0].payload, EntityUpdatedPayload)
    changed = update_events[0].payload.changed_fields
    assert "title" in changed
    assert changed["title"].before == "Engineer"
    assert changed["title"].after == "Senior Engineer"
    assert "name" not in changed  # name was not changed


def test_update_entity_record_no_changes_emits_no_event(mgr) -> None:
    _, entity_id = _seed_entity(mgr)
    before_count = mgr.list_entity_events_for_actor(_actor(), entity_id).total
    mgr.update_entity_record_for_actor(
        _actor(),
        entity_id,
        EntityRecordUpdateRequest(data={"name": "Alice", "title": "Engineer", "salary": "100k"}),
    )
    after_count = mgr.list_entity_events_for_actor(_actor(), entity_id).total
    assert after_count == before_count


def test_set_assignee_emits_entity_assignee_changed(mgr) -> None:
    _, entity_id = _seed_entity(mgr)
    mgr.set_entity_assignee_for_actor(_actor(), entity_id, "recruiter-99")
    listing = mgr.list_entity_events_for_actor(_actor(), entity_id)
    assignee_events = [
        e for e in listing.items if e.event_type == EntityAuditEventType.ASSIGNEE_CHANGED
    ]
    assert len(assignee_events) == 1
    assert isinstance(assignee_events[0].payload, EntityAssigneeChangedPayload)
    payload = assignee_events[0].payload
    assert payload.new_assignee_id == "recruiter-99"
    assert payload.previous_assignee_id is None


def test_remove_assignee_emits_assignee_changed_with_null_new_assignee(mgr) -> None:
    _, entity_id = _seed_entity(mgr)
    mgr.set_entity_assignee_for_actor(_actor(), entity_id, "recruiter-99")
    mgr.set_entity_assignee_for_actor(_actor(), entity_id, None)
    listing = mgr.list_entity_events_for_actor(_actor(), entity_id)
    unassign_event = [
        e
        for e in listing.items
        if e.event_type == EntityAuditEventType.ASSIGNEE_CHANGED
        and isinstance(e.payload, EntityAssigneeChangedPayload)
        and e.payload.new_assignee_id is None
    ]
    assert len(unassign_event) == 1
    assert isinstance(unassign_event[0].payload, EntityAssigneeChangedPayload)
    assert unassign_event[0].payload.previous_assignee_id == "recruiter-99"


def test_archive_entity_record_emits_entity_archived(mgr) -> None:
    _, entity_id = _seed_entity(mgr)
    mgr.archive_entity_record_for_actor(_actor(), entity_id)
    listing = mgr.list_entity_events_for_actor(_actor(), entity_id)
    archived = [e for e in listing.items if e.event_type == EntityAuditEventType.ARCHIVED]
    assert len(archived) == 1


def test_restore_entity_record_emits_entity_restored(mgr) -> None:
    _, entity_id = _seed_entity(mgr)
    mgr.archive_entity_record_for_actor(_actor(), entity_id)
    mgr.restore_entity_record_for_actor(_actor(), entity_id)
    listing = mgr.list_entity_events_for_actor(_actor(), entity_id)
    restored = [e for e in listing.items if e.event_type == EntityAuditEventType.RESTORED]
    assert len(restored) == 1


# ── Actor identity ────────────────────────────────────────────────────────────


def test_system_actor_identity_recorded_correctly(mgr) -> None:
    et_id = _seed_entity_type(mgr)
    sys_actor = build_system_actor(ORG, source="worker")
    record = mgr.create_entity_record_for_actor(
        sys_actor,
        EntityRecordCreateRequest(entity_type_id=et_id, data={"identifier": "sys-001", "name": "SystemCreated"}),
    )
    listing = mgr.list_entity_events_for_actor(_actor(), record.entity_id)
    event = listing.items[0]
    assert event.actor_type == "system"
    assert event.actor_name == "System"
    assert event.actor_role == "SYSTEM"
    assert event.actor_id is None


def test_system_and_human_actor_both_appear_in_timeline(mgr) -> None:
    _, entity_id = _seed_entity(mgr)
    sys_actor = build_system_actor(ORG, source="worker")
    mgr.update_entity_record_for_actor(
        sys_actor,
        entity_id,
        EntityRecordUpdateRequest(data={"title": "Updated by System"}),
    )
    listing = mgr.list_entity_events_for_actor(_actor(), entity_id)
    actor_types = {e.actor_type for e in listing.items}
    assert "user" in actor_types
    assert "system" in actor_types


def test_actor_name_is_none_when_user_not_in_db(mgr) -> None:
    """User "user-audit-test" is not seeded — actor_name should be None, not an error."""
    _, entity_id = _seed_entity(mgr)
    listing = mgr.list_entity_events_for_actor(_actor(), entity_id)
    created_event = next(e for e in listing.items if e.event_type == EntityAuditEventType.CREATED)
    assert created_event.actor_name is None
    assert created_event.actor_role is None


# ── Read API: sort order, pagination, filtering ───────────────────────────────


def test_list_entity_events_returns_newest_first(mgr) -> None:
    _, entity_id = _seed_entity(mgr)
    mgr.archive_entity_record_for_actor(_actor(), entity_id)
    mgr.restore_entity_record_for_actor(_actor(), entity_id)
    listing = mgr.list_entity_events_for_actor(_actor(), entity_id)
    assert listing.items[0].event_type == EntityAuditEventType.RESTORED
    assert listing.items[-1].event_type == EntityAuditEventType.CREATED


def test_list_entity_events_total_reflects_full_count(
    entities_db_service_manager, clean_entities_tables
) -> None:
    mgr = _build_manager(entities_db_service_manager)
    _, entity_id = _seed_entity(mgr)
    for i in range(10):
        mgr._emit_entity_event(
            organization_id=ORG,
            entity_id=entity_id,
            event_type=EntityAuditEventType.ARCHIVED,
            actor_type="system",
            idempotency_key=f"pad-{i}",
        )
    listing = mgr.list_entity_events_for_actor(_actor(), entity_id, limit=5, offset=0)
    assert listing.total >= 11  # 1 CREATED + 10 padded
    assert len(listing.items) == 5


def test_list_entity_events_pagination_offset(
    entities_db_service_manager, clean_entities_tables
) -> None:
    mgr = _build_manager(entities_db_service_manager)
    _, entity_id = _seed_entity(mgr)
    for i in range(5):
        mgr._emit_entity_event(
            organization_id=ORG,
            entity_id=entity_id,
            event_type=EntityAuditEventType.ARCHIVED,
            actor_type="system",
            idempotency_key=f"off-{i}",
        )
    page1 = mgr.list_entity_events_for_actor(_actor(), entity_id, limit=3, offset=0)
    page2 = mgr.list_entity_events_for_actor(_actor(), entity_id, limit=3, offset=3)
    assert len(page1.items) == 3
    assert len(page2.items) >= 1
    page1_ids = {e.event_id for e in page1.items}
    page2_ids = {e.event_id for e in page2.items}
    assert page1_ids.isdisjoint(page2_ids)


def test_list_entity_events_filter_by_event_type(mgr) -> None:
    _, entity_id = _seed_entity(mgr)
    mgr.archive_entity_record_for_actor(_actor(), entity_id)
    mgr.restore_entity_record_for_actor(_actor(), entity_id)
    listing = mgr.list_entity_events_for_actor(
        _actor(), entity_id, event_type=EntityAuditEventType.ARCHIVED
    )
    assert listing.total == 1
    assert listing.items[0].event_type == EntityAuditEventType.ARCHIVED


def test_list_entity_events_filter_returns_empty_when_no_match(mgr) -> None:
    _, entity_id = _seed_entity(mgr)
    listing = mgr.list_entity_events_for_actor(
        _actor(), entity_id, event_type=EntityAuditEventType.RESTORED
    )
    assert listing.total == 0
    assert listing.items == []


def test_list_entity_events_raises_not_found_for_unknown_entity(mgr) -> None:
    with pytest.raises(NotFoundError):
        mgr.list_entity_events_for_actor(_actor(), "does-not-exist")


def test_list_entity_events_raises_not_found_for_wrong_org(mgr) -> None:
    _, entity_id = _seed_entity(mgr)
    with pytest.raises(NotFoundError):
        mgr.list_entity_events_for_actor(_actor(org=OTHER_ORG), entity_id)


def test_list_entity_events_raises_authorization_error_when_denied(
    entities_db_service_manager, clean_entities_tables
) -> None:
    permissive = _build_manager(entities_db_service_manager)
    _, entity_id = _seed_entity(permissive)

    deny_mgr = _build_manager(
        entities_db_service_manager, roles_manager=_DenyEntityPermissionRolesManager()
    )
    with pytest.raises(AuthorizationError):
        deny_mgr.list_entity_events_for_actor(_actor(), entity_id)


def test_list_entity_events_raises_403_when_no_entity_type_view_permission(
    entities_db_service_manager, clean_entities_tables
) -> None:
    permissive = _build_manager(entities_db_service_manager)
    _, entity_id = _seed_entity(permissive)

    deny_mgr = _build_manager(
        entities_db_service_manager, roles_manager=_DenyEntityPermissionRolesManager()
    )
    with pytest.raises(AuthorizationError):
        deny_mgr.list_entity_events_for_actor(_actor(), entity_id)


# ── Field masking on ENTITY_UPDATED ──────────────────────────────────────────


def test_entity_updated_hidden_field_removed_from_changed_fields(
    entities_db_service_manager, clean_entities_tables
) -> None:
    # 'name' is visible, 'salary' is NOT in visible list -> removed entirely
    mgr = _build_manager(
        entities_db_service_manager,
        roles_manager=_RestrictedRolesManager(visible=["name", "title"], masked=[]),
    )
    _, entity_id = _seed_entity(mgr)
    mgr.update_entity_record_for_actor(
        _actor(),
        entity_id,
        EntityRecordUpdateRequest(data={"name": "Alice", "title": "Senior Engineer", "salary": "200k"}),
    )
    listing = mgr.list_entity_events_for_actor(_actor(), entity_id)
    update_event = next(e for e in listing.items if e.event_type == EntityAuditEventType.UPDATED)
    assert isinstance(update_event.payload, EntityUpdatedPayload)
    changed = update_event.payload.changed_fields
    assert "salary" not in changed
    assert "title" in changed


def test_entity_updated_masked_field_shows_stars(
    entities_db_service_manager, clean_entities_tables
) -> None:
    # 'salary' is visible but masked
    mgr = _build_manager(
        entities_db_service_manager,
        roles_manager=_RestrictedRolesManager(visible=["title", "salary"], masked=["salary"]),
    )
    _, entity_id = _seed_entity(mgr)
    mgr.update_entity_record_for_actor(
        _actor(),
        entity_id,
        EntityRecordUpdateRequest(data={"title": "Lead Engineer", "salary": "200k"}),
    )
    listing = mgr.list_entity_events_for_actor(_actor(), entity_id)
    update_event = next(e for e in listing.items if e.event_type == EntityAuditEventType.UPDATED)
    assert isinstance(update_event.payload, EntityUpdatedPayload)
    changed = update_event.payload.changed_fields
    assert "salary" in changed
    assert changed["salary"].before == "***"
    assert changed["salary"].after == "***"
    assert changed["title"].before == "Engineer"
    assert changed["title"].after == "Lead Engineer"


def test_entity_updated_fully_visible_field_returns_real_values(
    entities_db_service_manager, clean_entities_tables
) -> None:
    mgr = _build_manager(
        entities_db_service_manager,
        roles_manager=_RestrictedRolesManager(visible=["title"], masked=[]),
    )
    _, entity_id = _seed_entity(mgr)
    mgr.update_entity_record_for_actor(
        _actor(),
        entity_id,
        EntityRecordUpdateRequest(data={"title": "Principal Engineer"}),
    )
    listing = mgr.list_entity_events_for_actor(_actor(), entity_id)
    update_event = next(e for e in listing.items if e.event_type == EntityAuditEventType.UPDATED)
    assert isinstance(update_event.payload, EntityUpdatedPayload)
    changed = update_event.payload.changed_fields
    assert changed["title"].before == "Engineer"
    assert changed["title"].after == "Principal Engineer"


def test_non_updated_events_have_no_changed_fields_masking(mgr) -> None:
    _, entity_id = _seed_entity(mgr)
    mgr.archive_entity_record_for_actor(_actor(), entity_id)
    listing = mgr.list_entity_events_for_actor(_actor(), entity_id)
    archived_event = next(e for e in listing.items if e.event_type == EntityAuditEventType.ARCHIVED)
    assert isinstance(archived_event.payload, EntityArchivedPayload)


def test_all_changed_fields_hidden_results_in_empty_changed_fields(
    entities_db_service_manager, clean_entities_tables
) -> None:
    mgr = _build_manager(
        entities_db_service_manager,
        roles_manager=_RestrictedRolesManager(visible=[], masked=[]),
    )
    _, entity_id = _seed_entity(mgr)
    mgr.update_entity_record_for_actor(
        _actor(),
        entity_id,
        EntityRecordUpdateRequest(data={"title": "Senior Engineer"}),
    )
    listing = mgr.list_entity_events_for_actor(_actor(), entity_id)
    update_event = next(e for e in listing.items if e.event_type == EntityAuditEventType.UPDATED)
    assert isinstance(update_event.payload, EntityUpdatedPayload)
    assert update_event.payload.changed_fields == {}


# ── HTTP endpoint ─────────────────────────────────────────────────────────────


def test_get_entity_events_endpoint_happy_path(client) -> None:
    et_resp = client.post(
        "/entity-types",
        json={"name": "Candidate", "schema_definition": {"fields": []}},
        headers=HEADERS,
    )
    assert et_resp.status_code == 201
    et_id = et_resp.json()["entity_type_id"]

    rec_resp = client.post(
        "/entity-records",
        json={"entity_type_id": et_id, "data": {"identifier": "ep-001", "name": "Alice"}},
        headers=HEADERS,
    )
    assert rec_resp.status_code == 201
    entity_id = rec_resp.json()["entity_id"]

    resp = client.get(f"/entity-records/{entity_id}/events", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["entity_id"] == entity_id
    assert body["total"] >= 1
    assert isinstance(body["items"], list)
    assert body["items"][0]["event_type"] == EntityAuditEventType.CREATED


def test_get_entity_events_endpoint_returns_404_for_unknown_entity(client) -> None:
    resp = client.get("/entity-records/does-not-exist/events", headers=HEADERS)
    assert resp.status_code == 404


def test_get_entity_events_endpoint_returns_403_when_auth_denied(
    entities_db_service_manager, clean_entities_tables
) -> None:
    # Seed entity via permissive manager, then hit it via deny manager at HTTP level
    permissive = _build_manager(entities_db_service_manager)
    _, entity_id = _seed_entity(permissive)

    deny_mgr = _build_manager(
        entities_db_service_manager, roles_manager=_DenyEntityPermissionRolesManager()
    )
    controller = EntitiesRestController(deny_mgr)
    router = APIRouter()
    controller.prepare(router)
    app = FastAPI()
    app.include_router(router)
    deny_client = TestClient(app)

    resp = deny_client.get(f"/entity-records/{entity_id}/events", headers=HEADERS)
    assert resp.status_code == 403


def test_get_entity_events_endpoint_pagination_params(client) -> None:
    et_resp = client.post(
        "/entity-types",
        json={"name": "Candidate", "schema_definition": {"fields": []}},
        headers=HEADERS,
    )
    et_id = et_resp.json()["entity_type_id"]
    rec_resp = client.post(
        "/entity-records",
        json={"entity_type_id": et_id, "data": {"identifier": "pg-001"}},
        headers=HEADERS,
    )
    entity_id = rec_resp.json()["entity_id"]

    resp = client.get(
        f"/entity-records/{entity_id}/events?limit=1&offset=0", headers=HEADERS
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) <= 1


def test_get_entity_events_endpoint_event_type_filter(client) -> None:
    et_resp = client.post(
        "/entity-types",
        json={"name": "Candidate", "schema_definition": {"fields": []}},
        headers=HEADERS,
    )
    et_id = et_resp.json()["entity_type_id"]
    rec_resp = client.post(
        "/entity-records",
        json={"entity_type_id": et_id, "data": {"identifier": "ft-001"}},
        headers=HEADERS,
    )
    entity_id = rec_resp.json()["entity_id"]

    resp = client.get(
        f"/entity-records/{entity_id}/events?event_type={EntityAuditEventType.RESTORED}",
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 0
    assert resp.json()["items"] == []


def test_get_entity_events_response_shape(client) -> None:
    et_resp = client.post(
        "/entity-types",
        json={"name": "Candidate", "schema_definition": {"fields": []}},
        headers=HEADERS,
    )
    et_id = et_resp.json()["entity_type_id"]
    rec_resp = client.post(
        "/entity-records",
        json={"entity_type_id": et_id, "data": {"identifier": "shape-001"}},
        headers=HEADERS,
    )
    entity_id = rec_resp.json()["entity_id"]

    resp = client.get(f"/entity-records/{entity_id}/events", headers=HEADERS)
    body = resp.json()
    assert "organization_id" in body
    assert "entity_id" in body
    assert "total" in body
    assert "items" in body
    item = body["items"][0]
    assert "event_id" in item
    assert "event_type" in item
    assert "actor_type" in item
    assert "actor_id" in item
    assert "actor_name" in item
    assert "actor_role" in item
    assert "occurred_at" in item
    assert "payload" in item
