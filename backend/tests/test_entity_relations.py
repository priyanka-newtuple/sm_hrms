"""Tests for the runtime entity_relations endpoints."""

from __future__ import annotations

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from entities.controller import EntitiesRestController
from entities.db_models import EntitiesModelService
from entities.manager import EntitiesServiceManager


class _AlwaysAllowAuth:
    class _Decision:
        allowed = True
        reason = ""

    def check_access(self, _payload: dict[str, object]) -> "_AlwaysAllowAuth._Decision":
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


def _create_entity_type(client: TestClient, headers: dict, name: str = "Candidate") -> str:
    payload = {
        "name": name,
        "schema_definition": {"fields": [{"name": "email", "type": "email"}]},
        "version": 1,
        "is_active": True,
    }
    resp = client.post("/entity-types", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["entity_type_id"]


def _create_entity_record(
    client: TestClient, headers: dict, entity_type_id: str, email: str = "alice@example.com"
) -> str:
    payload = {
        "entity_type_id": entity_type_id,
        "data": {"email": email},
    }
    resp = client.post("/entity-records", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["entity_id"]


def _two_entities(client: TestClient, headers: dict) -> tuple[str, str]:
    et = _create_entity_type(client, headers)
    a = _create_entity_record(client, headers, et, email="a@example.com")
    b = _create_entity_record(client, headers, et, email="b@example.com")
    return a, b


def test_create_entity_relation_returns_relation(client) -> None:
    a, b = _two_entities(client, ADMIN_HEADERS)

    resp = client.post(
        f"/entities/{a}/relations",
        json={
            "from_entity_id": a,
            "to_entity_id": b,
            "relation_type": "APPLIED_TO",
            "relation_metadata": {"note": "primary"},
        },
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["organization_id"] == "test-org-1"
    assert body["from_entity_id"] == a
    assert body["to_entity_id"] == b
    assert body["relation_type"] == "APPLIED_TO"
    assert body["relation_metadata"] == {"note": "primary"}
    assert body["relation_id"]


def test_create_entity_relation_path_must_match_from(client) -> None:
    a, b = _two_entities(client, ADMIN_HEADERS)

    resp = client.post(
        f"/entities/{b}/relations",
        json={"from_entity_id": a, "to_entity_id": b, "relation_type": "APPLIED_TO"},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 400, resp.text
    assert "from_entity_id" in resp.text


def test_create_entity_relation_rejects_self_loop(client) -> None:
    """Pydantic model_validator catches this at body parse → 422."""
    a, _ = _two_entities(client, ADMIN_HEADERS)

    resp = client.post(
        f"/entities/{a}/relations",
        json={"from_entity_id": a, "to_entity_id": a, "relation_type": "REL"},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 422, resp.text


def test_create_entity_relation_duplicate_returns_409(client) -> None:
    a, b = _two_entities(client, ADMIN_HEADERS)
    payload = {"from_entity_id": a, "to_entity_id": b, "relation_type": "APPLIED_TO"}

    first = client.post(f"/entities/{a}/relations", json=payload, headers=ADMIN_HEADERS)
    assert first.status_code == 201, first.text
    second = client.post(f"/entities/{a}/relations", json=payload, headers=ADMIN_HEADERS)
    assert second.status_code == 409, second.text


def test_create_entity_relation_rejects_cross_org_endpoint(client) -> None:
    """Tenant isolation: cannot create a relation pointing at an entity in
    a different org, even if the UUID is known."""
    a, _ = _two_entities(client, ADMIN_HEADERS)
    et_other = _create_entity_type(client, OTHER_ORG_HEADERS)
    foreign = _create_entity_record(client, OTHER_ORG_HEADERS, et_other, email="foreign@example.com")

    resp = client.post(
        f"/entities/{a}/relations",
        json={"from_entity_id": a, "to_entity_id": foreign, "relation_type": "REL"},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 400, resp.text
    assert "not found" in resp.text.lower()


def test_create_entity_relation_requires_admin(client) -> None:
    a, b = _two_entities(client, ADMIN_HEADERS)
    resp = client.post(
        f"/entities/{a}/relations",
        json={"from_entity_id": a, "to_entity_id": b, "relation_type": "REL"},
        headers=READ_HEADERS,
    )
    assert resp.status_code == 403, resp.text


def test_list_entity_relations_default_both_directions(client) -> None:
    a, b = _two_entities(client, ADMIN_HEADERS)
    et = _create_entity_type(client, ADMIN_HEADERS, name="Job")
    c = _create_entity_record(client, ADMIN_HEADERS, et, email="c@example.com")

    # a → b, c → a
    client.post(
        f"/entities/{a}/relations",
        json={"from_entity_id": a, "to_entity_id": b, "relation_type": "APPLIED_TO"},
        headers=ADMIN_HEADERS,
    )
    client.post(
        f"/entities/{c}/relations",
        json={"from_entity_id": c, "to_entity_id": a, "relation_type": "REFERRED_BY"},
        headers=ADMIN_HEADERS,
    )

    resp = client.get(f"/entities/{a}/relations", headers=READ_HEADERS)
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 2
    types = {item["relation_type"] for item in items}
    assert types == {"APPLIED_TO", "REFERRED_BY"}


def test_list_entity_relations_filter_by_direction_and_type(client) -> None:
    a, b = _two_entities(client, ADMIN_HEADERS)
    et = _create_entity_type(client, ADMIN_HEADERS, name="Job")
    c = _create_entity_record(client, ADMIN_HEADERS, et, email="c@example.com")

    client.post(
        f"/entities/{a}/relations",
        json={"from_entity_id": a, "to_entity_id": b, "relation_type": "APPLIED_TO"},
        headers=ADMIN_HEADERS,
    )
    client.post(
        f"/entities/{a}/relations",
        json={"from_entity_id": a, "to_entity_id": c, "relation_type": "INTERVIEWED_FOR"},
        headers=ADMIN_HEADERS,
    )

    resp = client.get(
        f"/entities/{a}/relations?direction=out&relation_type=APPLIED_TO",
        headers=READ_HEADERS,
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["to_entity_id"] == b


def test_list_entity_relations_scoped_by_org(client) -> None:
    """An actor in org-2 listing an entity from org-1 sees no relations
    (the read is scoped to actor org)."""
    a, b = _two_entities(client, ADMIN_HEADERS)
    client.post(
        f"/entities/{a}/relations",
        json={"from_entity_id": a, "to_entity_id": b, "relation_type": "APPLIED_TO"},
        headers=ADMIN_HEADERS,
    )

    resp = client.get(f"/entities/{a}/relations", headers=OTHER_ORG_HEADERS)
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"] == []


def test_delete_entity_relation_removes_it(client) -> None:
    a, b = _two_entities(client, ADMIN_HEADERS)
    created = client.post(
        f"/entities/{a}/relations",
        json={"from_entity_id": a, "to_entity_id": b, "relation_type": "APPLIED_TO"},
        headers=ADMIN_HEADERS,
    ).json()
    relation_id = created["relation_id"]

    resp = client.delete(f"/entity-relations/{relation_id}", headers=ADMIN_HEADERS)
    assert resp.status_code == 200, resp.text
    assert resp.json()["relation_id"] == relation_id

    listed = client.get(f"/entities/{a}/relations", headers=READ_HEADERS)
    assert listed.json()["items"] == []


def test_delete_entity_relation_isolated_across_orgs(client) -> None:
    a, b = _two_entities(client, ADMIN_HEADERS)
    created = client.post(
        f"/entities/{a}/relations",
        json={"from_entity_id": a, "to_entity_id": b, "relation_type": "APPLIED_TO"},
        headers=ADMIN_HEADERS,
    ).json()
    relation_id = created["relation_id"]

    resp = client.delete(f"/entity-relations/{relation_id}", headers=OTHER_ORG_HEADERS)
    assert resp.status_code == 404, resp.text
