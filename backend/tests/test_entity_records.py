"""Tests for the runtime entity_records endpoints (state-machine rewrite, PR2a)."""

from __future__ import annotations

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from entities.controller import EntitiesRestController
from entities.db_models import EntitiesModelService
from entities.manager import EntitiesServiceManager
from entities.models.request import (
    EntityRecordCreateRequest,
    EntityRecordUpdateRequest,
    EntityTypeCreateRequest,
)


class _AlwaysAllowAuth:
    class _Decision:
        allowed = True
        reason = ""

    def check_access(self, _payload: dict[str, object]) -> _AlwaysAllowAuth._Decision:
        return self._Decision()


@pytest.fixture
def client(entities_db_service_manager, clean_entities_tables) -> TestClient:
    db_service = EntitiesModelService(database_service_manager=entities_db_service_manager)
    manager = EntitiesServiceManager(
        db_service,
        database_service_manager=entities_db_service_manager,
        config=None,
        auth_service_manager=_AlwaysAllowAuth(),
    )
    manager.start()

    controller = EntitiesRestController(manager)
    router = APIRouter()
    controller.prepare(router)

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


ADMIN_HEADERS = {
    "x-user-id": "admin-user",
    "x-org-id": "test-org-1",
    "x-user-roles": "admin",
}
READ_HEADERS = {
    "x-user-id": "viewer-user",
    "x-org-id": "test-org-1",
    "x-user-roles": "viewer",
}
OTHER_ORG_HEADERS = {
    "x-user-id": "other-admin",
    "x-org-id": "test-org-2",
    "x-user-roles": "admin",
}


def _entity_type_payload(name: str = "Candidate") -> dict:
    return {
        "name": name,
        "schema_definition": {"fields": [{"name": "email", "type": "email"}]},
        "version": 1,
        "is_active": True,
    }


def _create_entity_type(client: TestClient, headers: dict, name: str = "Candidate") -> str:
    resp = client.post("/entity-types", json=_entity_type_payload(name=name), headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["entity_type_id"]


def _record_payload(entity_type_id: str) -> dict:
    return {
        "entity_type_id": entity_type_id,
        "data": {"email": "alice@example.com", "name": "Alice"},
        "owner_id": "recruiter-1",
    }


def test_create_entity_record_returns_record(client) -> None:
    et_id = _create_entity_type(client, ADMIN_HEADERS)

    resp = client.post("/entity-records", json=_record_payload(et_id), headers=ADMIN_HEADERS)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["organization_id"] == "test-org-1"
    assert body["entity_type_id"] == et_id
    assert body["data"]["email"] == "alice@example.com"
    assert body["owner_id"] == "recruiter-1"
    assert body["entity_id"]
    assert body["archived_at"] is None


def test_duplicate_identifier_rejected_within_entity_type(client) -> None:
    et_id = _create_entity_type(client, ADMIN_HEADERS)

    first = client.post(
        "/entity-records",
        json={"entity_type_id": et_id, "data": {"identifier": "ACME-001"}},
        headers=ADMIN_HEADERS,
    )
    assert first.status_code == 201, first.text

    dup = client.post(
        "/entity-records",
        json={"entity_type_id": et_id, "data": {"identifier": "ACME-001"}},
        headers=ADMIN_HEADERS,
    )
    assert dup.status_code == 400, dup.text

    # A different identifier of the same type is accepted.
    other = client.post(
        "/entity-records",
        json={"entity_type_id": et_id, "data": {"identifier": "ACME-002"}},
        headers=ADMIN_HEADERS,
    )
    assert other.status_code == 201, other.text


def test_same_identifier_allowed_across_entity_types(client) -> None:
    et_a = _create_entity_type(client, ADMIN_HEADERS)
    et_b = _create_entity_type(client, ADMIN_HEADERS, name="Job")

    a = client.post(
        "/entity-records",
        json={"entity_type_id": et_a, "data": {"identifier": "SHARED-1"}},
        headers=ADMIN_HEADERS,
    )
    b = client.post(
        "/entity-records",
        json={"entity_type_id": et_b, "data": {"identifier": "SHARED-1"}},
        headers=ADMIN_HEADERS,
    )
    assert a.status_code == 201, a.text
    assert b.status_code == 201, b.text


def test_list_entity_records_scoped_by_org(client) -> None:
    et_id_1 = _create_entity_type(client, ADMIN_HEADERS)
    et_id_2 = _create_entity_type(client, OTHER_ORG_HEADERS)

    client.post("/entity-records", json=_record_payload(et_id_1), headers=ADMIN_HEADERS)
    client.post("/entity-records", json=_record_payload(et_id_2), headers=OTHER_ORG_HEADERS)

    resp = client.get("/entity-records", headers=READ_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["organization_id"] == "test-org-1"
    assert len(body["items"]) == 1


def test_list_entity_records_filter_by_entity_type(client) -> None:
    et_a = _create_entity_type(client, ADMIN_HEADERS)
    et_b = _create_entity_type(client, ADMIN_HEADERS, name="Job")

    client.post("/entity-records", json=_record_payload(et_a), headers=ADMIN_HEADERS)
    client.post("/entity-records", json=_record_payload(et_b), headers=ADMIN_HEADERS)

    resp = client.get(
        f"/entity-records?entity_type_id={et_a}",
        headers=READ_HEADERS,
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["entity_type_id"] == et_a


def test_entity_record_summary_is_bounded_and_detail_remains_full(
    entities_db_service_manager, clean_entities_tables
) -> None:
    db_service = EntitiesModelService(database_service_manager=entities_db_service_manager)
    manager = EntitiesServiceManager(
        db_service,
        database_service_manager=entities_db_service_manager,
        config=None,
        auth_service_manager=_AlwaysAllowAuth(),
    )
    manager.start()
    actor = {"user_id": "viewer-user", "organization_id": "test-org-1", "roles": ["viewer"]}
    entity_type_id = manager.create_entity_type_for_actor(
        actor, EntityTypeCreateRequest(name="Candidate")
    ).entity_type_id
    entity_ids: list[str] = []
    for index in range(3):
        created = manager.create_entity_record(
            EntityRecordCreateRequest(
                organization_id="test-org-1",
                entity_type_id=entity_type_id,
                data={
                    "identifier": f"C-{index}",
                    "email": f"candidate-{index}@example.com",
                    "private_note": "detail only",
                },
            )
        )
        entity_ids.append(created.entity_id)

    first = manager.list_entity_record_summaries_for_actor(
        actor,
        entity_type_name="Candidate",
        fields={"email"},
        limit=2,
    )
    assert len(first.items) == 2
    assert first.has_more is True
    assert first.next_cursor
    assert all("private_note" not in item.summary_fields for item in first.items)

    second = manager.list_entity_record_summaries_for_actor(
        actor,
        entity_type_name="Candidate",
        fields={"email"},
        limit=2,
        cursor=first.next_cursor,
    )
    assert len(second.items) == 1

    detail = manager.get_entity_record(organization_id="test-org-1", entity_id=entity_ids[0])
    assert detail is not None
    assert detail.data["private_note"] == "detail only"


def test_get_entity_record_by_id(client) -> None:
    et_id = _create_entity_type(client, ADMIN_HEADERS)
    created = client.post(
        "/entity-records", json=_record_payload(et_id), headers=ADMIN_HEADERS
    ).json()
    entity_id = created["entity_id"]

    resp = client.get(
        f"/entity-records/{entity_id}",
        headers=READ_HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["entity_id"] == entity_id


def test_get_entity_record_isolated_across_orgs(client) -> None:
    et_id = _create_entity_type(client, ADMIN_HEADERS)
    created = client.post(
        "/entity-records", json=_record_payload(et_id), headers=ADMIN_HEADERS
    ).json()
    entity_id = created["entity_id"]

    resp = client.get(
        f"/entity-records/{entity_id}",
        headers=OTHER_ORG_HEADERS,
    )
    assert resp.status_code == 404


def test_update_entity_record_partial(client) -> None:
    et_id = _create_entity_type(client, ADMIN_HEADERS)
    created = client.post(
        "/entity-records", json=_record_payload(et_id), headers=ADMIN_HEADERS
    ).json()
    entity_id = created["entity_id"]

    resp = client.put(
        f"/entity-records/{entity_id}",
        json={"data": {"email": "alice@new.com"}, "owner_id": "recruiter-2"},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["email"] == "alice@new.com"
    assert body["owner_id"] == "recruiter-2"


def test_timer_duration_final_number_uses_the_normal_entity_update(
    entities_db_service_manager, clean_entities_tables
) -> None:
    db_service = EntitiesModelService(database_service_manager=entities_db_service_manager)
    manager = EntitiesServiceManager(
        db_service,
        database_service_manager=entities_db_service_manager,
        config=None,
        auth_service_manager=_AlwaysAllowAuth(),
    )
    entity_type = db_service.create_entity_type(
        EntityTypeCreateRequest(
            organization_id="test-org-1",
            name="Request",
            schema_definition={
                "fields": [{"name": "elapsed_seconds", "type": "timer_duration"}]
            },
        )
    )
    created = db_service.create_entity_record(
        request=EntityRecordCreateRequest(
            organization_id="test-org-1",
            entity_type_id=entity_type.entity_type_id,
            data={},
        )
    )

    updated = manager.update_entity_record(
        organization_id="test-org-1",
        entity_id=created.entity_id,
        request=EntityRecordUpdateRequest(data={"elapsed_seconds": 90}),
    )

    assert updated is not None
    assert updated.data["elapsed_seconds"] == 90


def test_entity_due_date_is_first_class_and_clearable(client) -> None:
    et_id = _create_entity_type(client, ADMIN_HEADERS)
    payload = _record_payload(et_id)
    payload["due_date"] = "2026-08-15"
    created = client.post("/entity-records", json=payload, headers=ADMIN_HEADERS)

    assert created.status_code == 201, created.text
    entity_id = created.json()["entity_id"]
    assert created.json()["due_date"] == "2026-08-15"
    assert "due_date" not in created.json()["data"]

    cleared = client.put(
        f"/entity-records/{entity_id}",
        json={"due_date": None},
        headers=ADMIN_HEADERS,
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["due_date"] is None


def test_archive_entity_record_hides_from_default_list(client) -> None:
    et_id = _create_entity_type(client, ADMIN_HEADERS)
    created = client.post(
        "/entity-records", json=_record_payload(et_id), headers=ADMIN_HEADERS
    ).json()
    entity_id = created["entity_id"]

    resp = client.delete(
        f"/entity-records/{entity_id}",
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["archived_at"] is not None

    listed = client.get("/entity-records", headers=READ_HEADERS)
    assert listed.status_code == 200
    assert listed.json()["items"] == []

    listed_all = client.get(
        "/entity-records?include_archived=true",
        headers=READ_HEADERS,
    )
    assert len(listed_all.json()["items"]) == 1


def test_create_entity_record_requires_admin(client) -> None:
    et_id = _create_entity_type(client, ADMIN_HEADERS)
    resp = client.post("/entity-records", json=_record_payload(et_id), headers=READ_HEADERS)
    assert resp.status_code == 403


def test_create_entity_record_rejects_cross_org_entity_type(client) -> None:
    """Tenant isolation: org-A cannot attach a record to an entity_type
    owned by org-B even if the entity_type_id UUID is known."""
    org_b_et_id = _create_entity_type(client, OTHER_ORG_HEADERS)

    resp = client.post(
        "/entity-records",
        json=_record_payload(org_b_et_id),
        headers=ADMIN_HEADERS,  # org-A actor referencing org-B's type
    )
    assert resp.status_code == 400, resp.text
    assert "not found" in resp.text.lower()


def test_restore_entity_record_clears_archived_at(client) -> None:
    et_id = _create_entity_type(client, ADMIN_HEADERS)
    created = client.post(
        "/entity-records", json=_record_payload(et_id), headers=ADMIN_HEADERS
    ).json()
    entity_id = created["entity_id"]
    client.delete(f"/entity-records/{entity_id}", headers=ADMIN_HEADERS)

    resp = client.post(
        f"/entity-records/{entity_id}/restore",
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["archived_at"] is None
    assert resp.json()["entity_id"] == entity_id


def test_restore_entity_record_404_when_missing(client) -> None:
    resp = client.post(
        "/entity-records/does-not-exist/restore",
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 404


def test_restore_entity_record_requires_admin(client) -> None:
    et_id = _create_entity_type(client, ADMIN_HEADERS)
    created = client.post(
        "/entity-records", json=_record_payload(et_id), headers=ADMIN_HEADERS
    ).json()
    entity_id = created["entity_id"]
    resp = client.post(
        f"/entity-records/{entity_id}/restore",
        headers=READ_HEADERS,
    )
    assert resp.status_code == 403


def test_get_entity_with_states_returns_entity_and_empty_states(client) -> None:
    et_id = _create_entity_type(client, ADMIN_HEADERS)
    created = client.post(
        "/entity-records", json=_record_payload(et_id), headers=ADMIN_HEADERS
    ).json()
    entity_id = created["entity_id"]

    resp = client.get(
        f"/entity-records/{entity_id}/with-states",
        headers=READ_HEADERS,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["entity"]["entity_id"] == entity_id
    assert body["states"] == []


def test_get_entity_with_states_404_when_missing(client) -> None:
    resp = client.get(
        "/entity-records/missing/with-states",
        headers=READ_HEADERS,
    )
    assert resp.status_code == 404


def test_create_entity_record_rejects_archived_entity_type(client) -> None:
    et_id = _create_entity_type(client, ADMIN_HEADERS)
    archive_resp = client.delete("/entity-types/Candidate", headers=ADMIN_HEADERS)
    assert archive_resp.status_code == 200, archive_resp.text

    resp = client.post("/entity-records", json=_record_payload(et_id), headers=ADMIN_HEADERS)
    assert resp.status_code == 400, resp.text
    assert "not active" in resp.text.lower()


def test_record_summaries_are_ordered_by_most_recent_update(
    entities_db_service_manager, clean_entities_tables
) -> None:
    """Records list defaults to most recently updated first.

    It used to come back oldest-created first. Keyset paginated, so this also
    checks a cursor page keeps the order without repeating or skipping a row.
    """
    db_service = EntitiesModelService(database_service_manager=entities_db_service_manager)
    manager = EntitiesServiceManager(
        db_service,
        database_service_manager=entities_db_service_manager,
        config=None,
        auth_service_manager=_AlwaysAllowAuth(),
    )
    manager.start()
    # System actor: field-level RBAC is covered elsewhere, this test is only
    # about the order rows come back in.
    actor = {
        "user_id": "admin-1",
        "organization_id": "test-org-1",
        "roles": ["admin"],
        "actor_type": "system",
    }
    entity_type_id = manager.create_entity_type_for_actor(
        actor, EntityTypeCreateRequest(name="RecencyCandidate")
    ).entity_type_id

    created_order: list[str] = []
    for index in range(3):
        created = manager.create_entity_record(
            EntityRecordCreateRequest(
                organization_id="test-org-1",
                entity_type_id=entity_type_id,
                data={"identifier": f"R-{index}"},
            )
        )
        created_order.append(created.entity_id)

    # Touch the OLDEST record: it must jump to the top.
    oldest = created_order[0]
    manager.update_entity_record_data(
        organization_id="test-org-1", entity_id=oldest, data={"identifier": "R-0-touched"}
    )

    page = manager.list_entity_record_summaries_for_actor(
        actor, entity_type_name="RecencyCandidate", fields={"identifier"}, limit=10
    )
    ids = [item.entity_id for item in page.items]
    assert ids[0] == oldest, "the most recently updated record must come first"
    assert set(ids) == set(created_order)
    # Non-increasing update timestamps across the page.
    stamps = [item.updated_at for item in page.items]
    assert stamps == sorted(stamps, reverse=True)

    # Same order across a cursor boundary, with no repeat and no gap.
    first = manager.list_entity_record_summaries_for_actor(
        actor, entity_type_name="RecencyCandidate", fields={"identifier"}, limit=2
    )
    second = manager.list_entity_record_summaries_for_actor(
        actor,
        entity_type_name="RecencyCandidate",
        fields={"identifier"},
        limit=2,
        cursor=first.next_cursor,
    )
    paged = [item.entity_id for item in first.items] + [item.entity_id for item in second.items]
    assert paged == ids
    assert len(set(paged)) == len(paged)
