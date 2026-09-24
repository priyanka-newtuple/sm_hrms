"""Tests for the canonical entity_types registry (state-machine rewrite, PR2b)."""

from __future__ import annotations

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


import pytest


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


def _candidate_payload(name: str = "Candidate", version: int = 1) -> dict:
    return {
        "name": name,
        "description": "A person applying to a role",
        "schema_definition": {
            "fields": [
                {"name": "name", "type": "string", "required": True},
                {"name": "email", "type": "email", "required": True},
            ]
        },
        "version": version,
        "is_active": True,
    }


def test_create_entity_type_returns_record(client) -> None:

    resp = client.post("/entity-types", json=_candidate_payload(), headers=ADMIN_HEADERS)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Candidate"
    assert body["organization_id"] == "test-org-1"
    assert body["version"] == 1
    assert body["is_active"] is True
    assert body["entity_type_id"]
    assert body["schema_definition"]["fields"][0]["name"] == "name"


def test_create_entity_type_rejects_duplicate_org_name_version(client) -> None:
    first = client.post("/entity-types", json=_candidate_payload(), headers=ADMIN_HEADERS)
    assert first.status_code == 201

    duplicate = client.post("/entity-types", json=_candidate_payload(), headers=ADMIN_HEADERS)
    assert duplicate.status_code == 409


def test_list_entity_types_scoped_by_org(client) -> None:

    client.post("/entity-types", json=_candidate_payload(), headers=ADMIN_HEADERS)
    client.post("/entity-types", json=_candidate_payload(), headers=OTHER_ORG_HEADERS)

    resp = client.get("/entity-types", headers=READ_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["organization_id"] == "test-org-1"
    assert len(body["items"]) == 1
    assert body["items"][0]["name"] == "Candidate"


def test_get_entity_type_by_name(client) -> None:
    client.post("/entity-types", json=_candidate_payload(), headers=ADMIN_HEADERS)

    resp = client.get("/entity-types/Candidate", headers=READ_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Candidate"


def test_get_entity_type_returns_404_when_missing(client) -> None:
    resp = client.get("/entity-types/Nonexistent", headers=READ_HEADERS)
    assert resp.status_code == 404


def test_get_entity_type_isolated_across_orgs(client) -> None:
    client.post("/entity-types", json=_candidate_payload(), headers=ADMIN_HEADERS)

    resp = client.get("/entity-types/Candidate", headers=OTHER_ORG_HEADERS)
    assert resp.status_code == 404


def test_update_entity_type_partial(client) -> None:
    client.post("/entity-types", json=_candidate_payload(), headers=ADMIN_HEADERS)

    resp = client.put(
        "/entity-types/Candidate",
        json={"description": "Updated description", "is_active": False},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["description"] == "Updated description"
    assert body["is_active"] is False
    assert body["name"] == "Candidate"


def test_update_entity_type_returns_409_on_name_conflict(client) -> None:
    first = _candidate_payload(name="Candidate")
    second = _candidate_payload(name="Employee")
    assert client.post("/entity-types", json=first, headers=ADMIN_HEADERS).status_code == 201
    assert client.post("/entity-types", json=second, headers=ADMIN_HEADERS).status_code == 201

    resp = client.put(
        "/entity-types/Candidate",
        json={"name": "Employee"},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 409


def test_archive_entity_type_sets_is_active_false(client) -> None:
    client.post("/entity-types", json=_candidate_payload(), headers=ADMIN_HEADERS)

    resp = client.delete("/entity-types/Candidate", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


def test_create_entity_type_requires_admin(client) -> None:
    resp = client.post("/entity-types", json=_candidate_payload(), headers=READ_HEADERS)
    assert resp.status_code == 403


def test_create_entity_type_validates_name(client) -> None:
    payload = _candidate_payload()
    payload["name"] = "   "
    resp = client.post("/entity-types", json=payload, headers=ADMIN_HEADERS)
    assert resp.status_code in (400, 422)


def test_create_list_and_delete_entity_type_relation(client) -> None:
    candidate = client.post("/entity-types", json=_candidate_payload(), headers=ADMIN_HEADERS)
    assert candidate.status_code == 201, candidate.text
    candidate_id = candidate.json()["entity_type_id"]

    job = client.post(
        "/entity-types",
        json=_candidate_payload(name="Job"),
        headers=ADMIN_HEADERS,
    )
    assert job.status_code == 201, job.text
    job_id = job.json()["entity_type_id"]

    create_resp = client.post(
        f"/entity-types/{candidate_id}/relations",
        json={
            "to_entity_type_id": job_id,
            "relation_name": "applied_to",
        },
        headers=ADMIN_HEADERS,
    )
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    assert created["from_entity_type_id"] == candidate_id
    assert created["to_entity_type_id"] == job_id
    assert created["relation_name"] == "APPLIED_TO"
    assert created["relation_def_id"]

    list_resp = client.get(
        f"/entity-types/{candidate_id}/relations",
        headers=READ_HEADERS,
    )
    assert list_resp.status_code == 200, list_resp.text
    listed = list_resp.json()
    assert listed["organization_id"] == "test-org-1"
    assert len(listed["items"]) == 1
    assert listed["items"][0]["relation_def_id"] == created["relation_def_id"]

    delete_resp = client.delete(
        f"/entity-types/{candidate_id}/relations/{created['relation_def_id']}",
        headers=ADMIN_HEADERS,
    )
    assert delete_resp.status_code == 204, delete_resp.text

    list_after_delete = client.get(
        f"/entity-types/{candidate_id}/relations",
        headers=READ_HEADERS,
    )
    assert list_after_delete.status_code == 200, list_after_delete.text
    assert list_after_delete.json()["items"] == []


def test_create_entity_type_relation_rejects_missing_target_type(client) -> None:
    candidate = client.post("/entity-types", json=_candidate_payload(), headers=ADMIN_HEADERS)
    assert candidate.status_code == 201, candidate.text
    candidate_id = candidate.json()["entity_type_id"]

    resp = client.post(
        f"/entity-types/{candidate_id}/relations",
        json={
            "to_entity_type_id": "missing-type-id",
            "relation_name": "applied_to",
        },
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 400, resp.text


# ── Identifier template config validation (STAT-353, spec §7) ────────────────


def _type_with_identifier(name: str, schema_definition: dict) -> dict:
    return {"name": name, "schema_definition": schema_definition}


def test_identifier_template_unknown_token_rejected(client) -> None:
    resp = client.post(
        "/entity-types",
        json=_type_with_identifier(
            "tpl_unknown",
            {
                "fields": [{"name": "first_name", "type": "string"}],
                "identifier_template": "{{ghost}}",
            },
        ),
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 400, resp.text
    assert "ghost" in resp.text


def test_identifier_template_literal_only_rejected(client) -> None:
    resp = client.post(
        "/entity-types",
        json=_type_with_identifier("tpl_literal", {"identifier_template": "NOTOKENS-"}),
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 400, resp.text


def test_identifier_template_seq_only_valid_without_forms(client) -> None:
    resp = client.post(
        "/entity-types",
        json=_type_with_identifier("tpl_seq_only", {"identifier_template": "INV-{{seq}}"}),
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 201, resp.text


def test_identifier_label_length_capped(client) -> None:
    resp = client.post(
        "/entity-types",
        json=_type_with_identifier("tpl_label_cap", {"identifier_label": "x" * 65}),
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 400, resp.text


def test_identifier_template_unsupported_field_type_rejected(client) -> None:
    resp = client.post(
        "/entity-types",
        json=_type_with_identifier(
            "tpl_bad_type",
            {
                "fields": [{"name": "lines", "type": "table"}],
                "identifier_template": "{{lines}}",
            },
        ),
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 400, resp.text
    assert "lines" in resp.text


def test_field_rename_rewrites_template(client) -> None:
    created = client.post(
        "/entity-types",
        json=_type_with_identifier(
            "tpl_rename",
            {
                "fields": [{"name": "first_name", "type": "string"}],
                "identifier_template": "{{first_name}}-{{seq}}",
            },
        ),
        headers=ADMIN_HEADERS,
    )
    assert created.status_code == 201, created.text

    updated = client.put(
        "/entity-types/tpl_rename",
        json={
            "schema_definition": {
                "fields": [{"name": "given_name", "type": "string"}],
                "identifier_template": "{{first_name}}-{{seq}}",
            }
        },
        headers=ADMIN_HEADERS,
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["schema_definition"]["identifier_template"] == "{{given_name}}-{{seq}}"


def test_field_reorder_does_not_rewrite_template(client) -> None:
    """Reordering fields is not a rename — the sequential positional rewrite
    used to corrupt swaps ({{a}}-{{b}} → {{a}}-{{a}})."""
    created = client.post(
        "/entity-types",
        json=_type_with_identifier(
            "tpl_reorder",
            {
                "fields": [
                    {"name": "first_name", "type": "string"},
                    {"name": "last_name", "type": "string"},
                ],
                "identifier_template": "{{first_name}}-{{last_name}}",
            },
        ),
        headers=ADMIN_HEADERS,
    )
    assert created.status_code == 201, created.text

    updated = client.put(
        "/entity-types/tpl_reorder",
        json={
            "schema_definition": {
                "fields": [
                    {"name": "last_name", "type": "string"},
                    {"name": "first_name", "type": "string"},
                ],
                "identifier_template": "{{first_name}}-{{last_name}}",
            }
        },
        headers=ADMIN_HEADERS,
    )
    assert updated.status_code == 200, updated.text
    assert (
        updated.json()["schema_definition"]["identifier_template"]
        == "{{first_name}}-{{last_name}}"
    )


def test_field_delete_does_not_misdetect_rename(client) -> None:
    """Deleting a field shifts every later position; shifted pairs must not be
    treated as renames."""
    created = client.post(
        "/entity-types",
        json=_type_with_identifier(
            "tpl_shrink",
            {
                "fields": [
                    {"name": "first_name", "type": "string"},
                    {"name": "last_name", "type": "string"},
                    {"name": "middle_name", "type": "string"},
                ],
                "identifier_template": "{{last_name}}-{{seq}}",
            },
        ),
        headers=ADMIN_HEADERS,
    )
    assert created.status_code == 201, created.text

    updated = client.put(
        "/entity-types/tpl_shrink",
        json={
            "schema_definition": {
                "fields": [
                    {"name": "last_name", "type": "string"},
                    {"name": "middle_name", "type": "string"},
                ],
                "identifier_template": "{{last_name}}-{{seq}}",
            }
        },
        headers=ADMIN_HEADERS,
    )
    assert updated.status_code == 200, updated.text
    assert (
        updated.json()["schema_definition"]["identifier_template"]
        == "{{last_name}}-{{seq}}"
    )


def test_identifier_template_stray_braces_rejected(client) -> None:
    """`{client_identifier}}-{{seq}}` (typo, one brace missing) must not save —
    it would render the malformed part literally into every identifier."""
    resp = client.post(
        "/entity-types",
        json=_type_with_identifier(
            "tpl_stray_braces",
            {"identifier_template": "{client_identifier}}-{{seq}}"},
        ),
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 400, resp.text
    assert "malformed" in resp.text
