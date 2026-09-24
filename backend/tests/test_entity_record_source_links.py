"""Linking source records to an entity via update (STAT-356 follow-up).

An entity created without its source links yet (e.g. by an agent's create_entity
tool call, which has no notion of relation declarations) can have them attached
afterward by sending `source_entity_ids` on the same PUT /entity-records/{id}
update the create-form's Save button already issues.

Same harness as test_identifier_generation.py — real Postgres, in-process FastAPI app.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from entities.controller import EntitiesRestController
from entities.db_models import EntitiesModelService
from entities.manager import EntitiesServiceManager
from entities.models.interface import RelationType
from entities.models.request import (
    EntityRecordCreateRequest,
    EntityRelationDeclarationCreateRequest,
    EntityTypeCreateRequest,
)
from exceptions import ValidationError


class _AlwaysAllowAuth:
    class _Decision:
        allowed = True
        reason = ""

    def check_access(self, _payload: dict[str, object]) -> "_AlwaysAllowAuth._Decision":
        return self._Decision()


def _build_manager(entities_db_service_manager) -> EntitiesServiceManager:
    db_service = EntitiesModelService(database_service_manager=entities_db_service_manager)
    config = SimpleNamespace(
        _configuration=SimpleNamespace(
            entity_relations_configuration=SimpleNamespace(default_relation_type="REFERENCE")
        )
    )
    manager = EntitiesServiceManager(
        db_service,
        database_service_manager=entities_db_service_manager,
        config=config,
        auth_service_manager=_AlwaysAllowAuth(),
    )
    manager.start()
    return manager


@pytest.fixture
def client(entities_db_service_manager, clean_entities_tables) -> TestClient:
    manager = _build_manager(entities_db_service_manager)
    controller = EntitiesRestController(manager)
    router = APIRouter()
    controller.prepare(router)

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def manager(entities_db_service_manager, clean_entities_tables) -> EntitiesServiceManager:
    return _build_manager(entities_db_service_manager)


ADMIN_ACTOR = {
    "user_id": "admin-user",
    "organization_id": "test-org-1",
    "roles": ["admin"],
    "request_id": None,
}


ADMIN_HEADERS = {
    "x-user-id": "admin-user",
    "x-org-id": "test-org-1",
    "x-user-roles": "admin",
}


def _create_type(client: TestClient, name: str, fields: list[dict] | None = None) -> str:
    resp = client.post(
        "/entity-types",
        json={
            "name": name,
            "schema_definition": {"fields": fields or [{"name": "name", "type": "string"}]},
        },
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["entity_type_id"]


def _declare_relation(
    client: TestClient, from_type_id: str, to_type_id: str, relation_type: str
) -> None:
    resp = client.post(
        f"/entity-types/{from_type_id}/relation-declarations",
        json={"to_entity_type_id": to_type_id, "relation_type": relation_type},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 201, resp.text


def _create_record(client: TestClient, entity_type_id: str, data: dict, **extra) -> dict:
    resp = client.post(
        "/entity-records",
        json={"entity_type_id": entity_type_id, "data": data, **extra},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _relations_of(client: TestClient, entity_id: str) -> list[dict]:
    resp = client.get(f"/entities/{entity_id}/relations", headers=ADMIN_HEADERS)
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


def test_update_links_source_entity_created_without_one(client) -> None:
    provider_type = _create_type(client, "provider_upd1")
    target_type = _create_type(client, "target_upd1")
    # SNAPSHOT, not REFERENCE: a REFERENCE declaration already requires the
    # source at creation time (existing, unrelated-to-this-fix behavior), so
    # "created without one, linked later" can only happen for SNAPSHOT — the
    # actual real-world shape of this bug (an agent's create_entity call has
    # no notion of relation declarations, so it never supplies either).
    _declare_relation(client, provider_type, target_type, "SNAPSHOT")

    provider = _create_record(client, provider_type, {"name": "Acme", "identifier": "acme"})
    target = _create_record(client, target_type, {"identifier": "target-1"})
    assert _relations_of(client, target["entity_id"]) == []

    resp = client.put(
        f"/entity-records/{target['entity_id']}",
        json={"source_entity_ids": [provider["entity_id"]]},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 200, resp.text

    relations = _relations_of(client, target["entity_id"])
    assert len(relations) == 1
    assert relations[0]["from_entity_id"] == provider["entity_id"]
    assert relations[0]["to_entity_id"] == target["entity_id"]
    assert relations[0]["relation_type"] == "SNAPSHOT"


def test_update_source_link_is_idempotent(client) -> None:
    provider_type = _create_type(client, "provider_upd2")
    target_type = _create_type(client, "target_upd2")
    _declare_relation(client, provider_type, target_type, "SNAPSHOT")

    provider = _create_record(client, provider_type, {"name": "Acme", "identifier": "acme2"})
    target = _create_record(client, target_type, {"identifier": "target-2"})

    for _ in range(2):
        resp = client.put(
            f"/entity-records/{target['entity_id']}",
            json={"source_entity_ids": [provider["entity_id"]]},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 200, resp.text

    # Second call must not insert a duplicate relation row for the same declaration.
    assert len(_relations_of(client, target["entity_id"])) == 1


def test_update_rejects_unknown_source_entity_id(client) -> None:
    provider_type = _create_type(client, "provider_upd3")
    target_type = _create_type(client, "target_upd3")
    _declare_relation(client, provider_type, target_type, "SNAPSHOT")
    target = _create_record(client, target_type, {"identifier": "target-3"})

    resp = client.put(
        f"/entity-records/{target['entity_id']}",
        json={"source_entity_ids": ["does-not-exist"]},
        headers=ADMIN_HEADERS,
    )
    # A ValidationError (unknown source record) must surface as 400, not a
    # generic 500 — update_entity_record needs the same except-ValidationError
    # passthrough create_entity_record already has.
    assert resp.status_code == 400, resp.text


# --- REFERENCE-source requirement (STAT-356) --------------------------------
# These exercise the manager directly (not the HTTP route) so they don't depend
# on the route-level permission service; the required-REFERENCE opt-out is a
# manager kwarg with no wire representation, so the manager is the right seam.


def _mgr_create_type(manager, name: str) -> str:
    record = manager.create_entity_type_for_actor(
        ADMIN_ACTOR,
        EntityTypeCreateRequest(
            organization_id="test-org-1",
            name=name,
            schema_definition={"fields": [{"name": "name", "type": "string"}]},
        ),
    )
    return record.entity_type_id


def _mgr_declare(manager, from_type: str, to_type: str, relation_type: str) -> None:
    manager.create_entity_relation_declaration_for_actor(
        ADMIN_ACTOR,
        EntityRelationDeclarationCreateRequest(
            organization_id="test-org-1",
            from_entity_type_id=from_type,
            to_entity_type_id=to_type,
            relation_type=RelationType(relation_type),
        ),
    )


def _mgr_relations(manager, entity_id: str) -> list:
    return manager.list_entity_relations_for_actor(ADMIN_ACTOR, entity_id).items


def test_create_requires_reference_source_by_default(manager) -> None:
    # Manual "Add Entity" path (default require_reference_sources=True): a
    # required REFERENCE declaration with no source supplied must still hard-fail,
    # so the opt-out added for agents does not weaken the UI form.
    provider_type = _mgr_create_type(manager, "provider_req1")
    target_type = _mgr_create_type(manager, "target_req1")
    _mgr_declare(manager, provider_type, target_type, "REFERENCE")

    with pytest.raises(ValidationError, match="linked record"):
        manager.create_entity_record_for_actor(
            ADMIN_ACTOR,
            EntityRecordCreateRequest(
                organization_id="test-org-1",
                entity_type_id=target_type,
                data={"identifier": "req-target-1"},
            ),
        )


def test_create_reference_optout_succeeds_without_source(manager) -> None:
    # Agent/document-driven path: require_reference_sources=False creates the
    # record even though the target type has a required REFERENCE declaration
    # and no source is supplied (STAT-356).
    provider_type = _mgr_create_type(manager, "provider_req2")
    target_type = _mgr_create_type(manager, "target_req2")
    _mgr_declare(manager, provider_type, target_type, "REFERENCE")

    record = manager.create_entity_record_for_actor(
        ADMIN_ACTOR,
        EntityRecordCreateRequest(
            organization_id="test-org-1",
            entity_type_id=target_type,
            data={"identifier": "req-target-2"},
        ),
        require_reference_sources=False,
    )

    # Created, with no relation row (the link is attached later).
    assert _mgr_relations(manager, record.entity_id) == []


def test_create_reference_optout_still_links_supplied_source(manager) -> None:
    # Opt-out only removes the *requirement*; a source that IS supplied must
    # still be linked (upload-with-owner path).
    provider_type = _mgr_create_type(manager, "provider_req3")
    target_type = _mgr_create_type(manager, "target_req3")
    _mgr_declare(manager, provider_type, target_type, "REFERENCE")

    provider = manager.create_entity_record_for_actor(
        ADMIN_ACTOR,
        EntityRecordCreateRequest(
            organization_id="test-org-1",
            entity_type_id=provider_type,
            data={"name": "Acme", "identifier": "acme-req3"},
        ),
    )
    record = manager.create_entity_record_for_actor(
        ADMIN_ACTOR,
        EntityRecordCreateRequest(
            organization_id="test-org-1",
            entity_type_id=target_type,
            data={"identifier": "req-target-3"},
            source_entity_ids=[provider.entity_id],
        ),
        require_reference_sources=False,
    )

    relations = _mgr_relations(manager, record.entity_id)
    assert len(relations) == 1
    assert relations[0].from_entity_id == provider.entity_id
    assert relations[0].relation_type == "REFERENCE"


def test_update_without_source_entity_ids_leaves_relations_untouched(client) -> None:
    provider_type = _create_type(client, "provider_upd4")
    target_type = _create_type(client, "target_upd4")
    _declare_relation(client, provider_type, target_type, "REFERENCE")

    provider = _create_record(client, provider_type, {"name": "Acme", "identifier": "acme4"})
    target = _create_record(
        client,
        target_type,
        {"identifier": "target-4"},
        source_entity_ids=[provider["entity_id"]],
    )
    assert len(_relations_of(client, target["entity_id"])) == 1

    # A plain data-only update (no source_entity_ids key at all) must not touch
    # the relation created at creation time.
    resp = client.put(
        f"/entity-records/{target['entity_id']}",
        json={"data": {"identifier": "target-4"}},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 200, resp.text
    assert len(_relations_of(client, target["entity_id"])) == 1
