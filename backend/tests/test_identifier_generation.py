"""Template-driven identifier generation (STAT-353).

Spec: design_docs/configurable_entity_identifier_spec_15Jul2026.MD §3-§7, §12.
Same harness as test_entity_records.py — real Postgres, in-process FastAPI app.
"""

from __future__ import annotations

from types import SimpleNamespace

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

    def check_access(self, _payload: dict[str, object]) -> _AlwaysAllowAuth._Decision:
        return self._Decision()


@pytest.fixture
def client(entities_db_service_manager, clean_entities_tables) -> TestClient:
    db_service = EntitiesModelService(database_service_manager=entities_db_service_manager)
    config = SimpleNamespace(
        _configuration=SimpleNamespace(
            entity_relations_configuration=SimpleNamespace(
                default_relation_type="REFERENCE"
            )
        )
    )
    manager = EntitiesServiceManager(
        db_service,
        database_service_manager=entities_db_service_manager,
        config=config,
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


def _create_type(
    client: TestClient,
    name: str,
    template: str | None = None,
    fields: list[dict] | None = None,
) -> str:
    schema_definition: dict = {
        "fields": fields
        if fields is not None
        else [
            {"name": "first_name", "type": "string"},
            {"name": "last_name", "type": "string"},
            {"name": "employee_number", "type": "string"},
            {"name": "client_name", "type": "string"},
        ]
    }
    if template is not None:
        schema_definition["identifier_template"] = template
    resp = client.post(
        "/entity-types",
        json={"name": name, "schema_definition": schema_definition},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["entity_type_id"]


def _create_record(
    client: TestClient, entity_type_id: str, data: dict, **extra
) -> dict:
    resp = client.post(
        "/entity-records",
        json={"entity_type_id": entity_type_id, "data": data, **extra},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_template_generates_identifier_and_ignores_client_value(client) -> None:
    et_id = _create_type(client, "cand_tpl", template="{{first_name}}-{{last_name}}")
    body = _create_record(
        client,
        et_id,
        {"first_name": "John", "last_name": "Smith", "identifier": "HACKED"},
    )
    assert body["data"]["identifier"] == "John-Smith"


def test_template_mode_client_duplicate_identifier_ignored(client) -> None:
    """A client-sent identifier equal to an existing one must not 409 in
    template mode — it is stripped before the insert and regenerated."""
    et_id = _create_type(
        client, "cand_dup_client", template="{{first_name}}-{{last_name}}"
    )
    first = _create_record(client, et_id, {"first_name": "John", "last_name": "Smith"})
    assert first["data"]["identifier"] == "John-Smith"

    second = _create_record(
        client,
        et_id,
        {"first_name": "Jane", "last_name": "Doe", "identifier": "John-Smith"},
    )
    assert second["data"]["identifier"] == "Jane-Doe"


def test_collision_appends_suffix(client) -> None:
    et_id = _create_type(client, "cand_dup", template="{{first_name}}-{{last_name}}")
    first = _create_record(client, et_id, {"first_name": "John", "last_name": "Smith"})
    second = _create_record(client, et_id, {"first_name": "John", "last_name": "Smith"})
    third = _create_record(client, et_id, {"first_name": "John", "last_name": "Smith"})
    assert first["data"]["identifier"] == "John-Smith"
    assert second["data"]["identifier"] == "John-Smith_2"
    assert third["data"]["identifier"] == "John-Smith_3"


def test_seq_scoped_per_prefix(client) -> None:
    et_id = _create_type(client, "filing_seq", template="{{client_name}}-{{seq}}")
    a1 = _create_record(client, et_id, {"client_name": "Acme"})
    g1 = _create_record(client, et_id, {"client_name": "Globex"})
    a2 = _create_record(client, et_id, {"client_name": "Acme"})
    assert a1["data"]["identifier"] == "Acme-0001"
    assert g1["data"]["identifier"] == "Globex-0001"
    assert a2["data"]["identifier"] == "Acme-0002"


def test_constant_prefix_seq_is_sequential(client) -> None:
    et_id = _create_type(client, "invoice_seq", template="INV-{{seq}}")
    first = _create_record(client, et_id, {})
    second = _create_record(client, et_id, {})
    assert first["data"]["identifier"] == "INV-0001"
    assert second["data"]["identifier"] == "INV-0002"


def test_blank_fields_skip_segments(client) -> None:
    et_id = _create_type(client, "cand_blank", template="{{first_name}}-{{employee_number}}")
    body = _create_record(client, et_id, {"first_name": "John"})
    assert body["data"]["identifier"] == "John"


def test_all_blank_falls_back_to_counter(client) -> None:
    et_id = _create_type(client, "cand_fallback", template="{{employee_number}}")
    first = _create_record(client, et_id, {})
    second = _create_record(client, et_id, {})
    assert first["data"]["identifier"] == "0001"
    assert second["data"]["identifier"] == "0002"


def test_unicode_values_preserved(client) -> None:
    et_id = _create_type(client, "cand_unicode", template="{{first_name}}-{{last_name}}")
    body = _create_record(client, et_id, {"first_name": "José", "last_name": "Müller"})
    assert body["data"]["identifier"] == "José-Müller"


def test_reference_token_resolves_from_source_link(client) -> None:
    client_type = _create_type(client, "client_ref", fields=[{"name": "name", "type": "string"}])
    filing_type = _create_type(client, "filing_ref", template="{{client_name}}-{{seq}}")

    decl = client.post(
        f"/entity-types/{client_type}/relation-declarations",
        json={
            "to_entity_type_id": filing_type,
            "relation_type": "REFERENCE",
            "relation_metadata": {"name": "client_name"},
        },
        headers=ADMIN_HEADERS,
    )
    assert decl.status_code == 201, decl.text

    acme = _create_record(client, client_type, {"name": "Acme", "identifier": "acme-co"})

    filing1 = _create_record(
        client, filing_type, {}, source_entity_ids=[acme["entity_id"]]
    )
    filing2 = _create_record(
        client, filing_type, {}, source_entity_ids=[acme["entity_id"]]
    )
    assert filing1["data"]["identifier"] == "Acme-0001"
    assert filing2["data"]["identifier"] == "Acme-0002"


def test_reference_token_sources_linked_entity_identifier(client) -> None:
    """The provider's own `identifier` is a valid reference source — mapping
    uses the dotted `provider.field -> target.field` format the form-config UI
    writes (ReferencePickerModal)."""
    client_type = _create_type(client, "client_idsrc", fields=[{"name": "name", "type": "string"}])
    filing_type = _create_type(
        client,
        "filing_idsrc",
        template="{{client_identifier}}-{{seq}}",
        fields=[{"name": "client_identifier", "type": "reference"}],
    )
    decl = client.post(
        f"/entity-types/{client_type}/relation-declarations",
        json={
            "to_entity_type_id": filing_type,
            "relation_type": "REFERENCE",
            "relation_metadata": {"client_idsrc.identifier": "filing_idsrc.client_identifier"},
        },
        headers=ADMIN_HEADERS,
    )
    assert decl.status_code == 201, decl.text

    acme = _create_record(
        client, client_type, {"name": "Acme Co", "identifier": "acme-co"}
    )
    filing = _create_record(client, filing_type, {}, source_entity_ids=[acme["entity_id"]])
    assert filing["data"]["identifier"] == "acme-co-0001"


def test_relation_only_identifier_token_no_form_field_needed(client) -> None:
    """`{{client_identifier}}` validates and resolves from the relation link
    alone — no reference form field, no mapping in relation_metadata."""
    client_type = _create_type(client, "client_rel_only", fields=[{"name": "name", "type": "string"}])
    filing_type = _create_type(client, "filing_rel_only", fields=[])

    decl = client.post(
        f"/entity-types/{client_type}/relation-declarations",
        json={"to_entity_type_id": filing_type, "relation_type": "REFERENCE"},
        headers=ADMIN_HEADERS,
    )
    assert decl.status_code == 201, decl.text

    # Template referencing the linked client's identifier — declaration-derived token.
    upd = client.put(
        "/entity-types/filing_rel_only",
        json={
            "schema_definition": {
                "fields": [],
                "identifier_template": "{{client_rel_only_identifier}}-{{seq}}",
            }
        },
        headers=ADMIN_HEADERS,
    )
    assert upd.status_code == 200, upd.text

    acme = _create_record(
        client, client_type, {"name": "Acme Co", "identifier": "acme-co"}
    )
    filing = _create_record(client, filing_type, {}, source_entity_ids=[acme["entity_id"]])
    assert filing["data"]["identifier"] == "acme-co-0001"

    second = _create_record(client, filing_type, {}, source_entity_ids=[acme["entity_id"]])
    assert second["data"]["identifier"] == "acme-co-0002"


def test_reference_token_without_link_blank_prefix(client) -> None:
    # A declared relation is mandatory in the existing entity model, so the
    # no-link case is represented by an unpopulated reference field on the
    # target schema rather than by creating an invalid relation instance.
    filing_type = _create_type(
        client,
        "filing_nolink",
        template="{{client_name}}-{{seq}}",
        fields=[{"name": "client_name", "type": "reference"}],
    )

    filing = _create_record(client, filing_type, {})
    assert filing["data"]["identifier"] == "0001"


def test_manual_mode_unchanged(client) -> None:
    et_id = _create_type(client, "cand_manual")  # no template
    first = client.post(
        "/entity-records",
        json={"entity_type_id": et_id, "data": {"identifier": "ACME-001"}},
        headers=ADMIN_HEADERS,
    )
    assert first.status_code == 201, first.text
    assert first.json()["data"]["identifier"] == "ACME-001"

    dup = client.post(
        "/entity-records",
        json={"entity_type_id": et_id, "data": {"identifier": "ACME-001"}},
        headers=ADMIN_HEADERS,
    )
    assert dup.status_code == 400, dup.text


def test_create_without_identifier_allowed_in_template_mode(client) -> None:
    et_id = _create_type(client, "cand_noid", template="{{first_name}}")
    body = _create_record(client, et_id, {"first_name": "Ann"})
    assert body["data"]["identifier"] == "Ann"


def test_update_cannot_change_generated_identifier(client) -> None:
    et_id = _create_type(client, "cand_lock", template="{{first_name}}-{{last_name}}")
    created = _create_record(client, et_id, {"first_name": "John", "last_name": "Smith"})
    entity_id = created["entity_id"]

    upd = client.put(
        f"/entity-records/{entity_id}",
        json={"data": {"identifier": "evil", "first_name": "Jon"}},
        headers=ADMIN_HEADERS,
    )
    assert upd.status_code == 200, upd.text

    fetched = client.get(f"/entity-records/{entity_id}", headers=ADMIN_HEADERS)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["data"]["identifier"] == "John-Smith"
    assert fetched.json()["data"]["first_name"] == "Jon"


def test_source_field_edit_does_not_change_identifier(client) -> None:
    et_id = _create_type(client, "cand_stable", template="{{first_name}}-{{last_name}}")
    created = _create_record(client, et_id, {"first_name": "John", "last_name": "Smith"})
    entity_id = created["entity_id"]

    upd = client.put(
        f"/entity-records/{entity_id}",
        json={"data": {"first_name": "Jonathan"}},
        headers=ADMIN_HEADERS,
    )
    assert upd.status_code == 200, upd.text
    fetched = client.get(f"/entity-records/{entity_id}", headers=ADMIN_HEADERS)
    assert fetched.json()["data"]["identifier"] == "John-Smith"


def test_manual_mode_update_still_allows_identifier_edit(client) -> None:
    et_id = _create_type(client, "cand_manual_edit")  # no template
    created = _create_record(client, et_id, {"identifier": "FIRST"})
    entity_id = created["entity_id"]

    upd = client.put(
        f"/entity-records/{entity_id}",
        json={"data": {"identifier": "SECOND"}},
        headers=ADMIN_HEADERS,
    )
    assert upd.status_code == 200, upd.text
    fetched = client.get(f"/entity-records/{entity_id}", headers=ADMIN_HEADERS)
    assert fetched.json()["data"]["identifier"] == "SECOND"


def test_manual_mode_update_to_taken_identifier_rejected(client) -> None:
    """Manual rename to an identifier another entity holds → readable 400,
    not a unique-index violation surfacing as a 500."""
    et_id = _create_type(client, "cand_manual_dup_edit")  # no template
    _create_record(client, et_id, {"identifier": "TAKEN"})
    other = _create_record(client, et_id, {"identifier": "MINE"})

    upd = client.put(
        f"/entity-records/{other['entity_id']}",
        json={"data": {"identifier": "TAKEN"}},
        headers=ADMIN_HEADERS,
    )
    assert upd.status_code == 400, upd.text
    assert "already exists" in upd.json()["detail"]
    fetched = client.get(
        f"/entity-records/{other['entity_id']}", headers=ADMIN_HEADERS
    )
    assert fetched.json()["data"]["identifier"] == "MINE"


def test_manual_mode_update_resending_own_identifier_ok(client) -> None:
    """Self-match must not trip the uniqueness check — clients echo the
    identifier back on every save."""
    et_id = _create_type(client, "cand_manual_self_edit")  # no template
    created = _create_record(client, et_id, {"identifier": "KEEP", "first_name": "A"})

    upd = client.put(
        f"/entity-records/{created['entity_id']}",
        json={"data": {"identifier": "KEEP", "first_name": "B"}},
        headers=ADMIN_HEADERS,
    )
    assert upd.status_code == 200, upd.text
    fetched = client.get(
        f"/entity-records/{created['entity_id']}", headers=ADMIN_HEADERS
    )
    assert fetched.json()["data"]["identifier"] == "KEEP"
    assert fetched.json()["data"]["first_name"] == "B"


def test_archived_identifier_is_reusable(client) -> None:
    """STAT-418: archiving a record frees its identifier — a new record that
    would generate the same base gets it back verbatim, not a _2 suffix."""
    et_id = _create_type(client, "cand_archived", template="{{first_name}}-{{last_name}}")
    created = _create_record(client, et_id, {"first_name": "John", "last_name": "Smith"})
    assert created["data"]["identifier"] == "John-Smith"
    archived = client.delete(
        f"/entity-records/{created['entity_id']}", headers=ADMIN_HEADERS
    )
    assert archived.status_code == 200, archived.text

    again = _create_record(client, et_id, {"first_name": "John", "last_name": "Smith"})
    assert again["data"]["identifier"] == "John-Smith"


def test_apply_identifier_template_without_entity_id(client, entities_db_service_manager) -> None:
    """Public/deferred form path shape: no relations, no service — reference
    tokens blank, field + seq tokens still work (spec §12 rows 34-35)."""
    from entities.db_models import EntityTypeModel, apply_identifier_template

    et_id = _create_type(client, "pf_type", template="PF-{{seq}}")
    session = entities_db_service_manager.postgres_db_service().get_db_session()
    try:
        type_model = (
            session.query(EntityTypeModel)
            .filter_by(organization_id="test-org-1", entity_type_id=et_id)
            .first()
        )
        out = apply_identifier_template(
            None,
            session,
            organization_id="test-org-1",
            entity_type=type_model,
            entity_id=None,
            data={"anything": "x"},
        )
        session.commit()
        assert out["identifier"] == "PF-0001"
    finally:
        session.close()


def test_manual_mode_duplicate_still_rejected_via_index_lookup(client) -> None:
    et_id = _create_type(client, "cand_manual_dup")
    first = client.post(
        "/entity-records",
        json={"entity_type_id": et_id, "data": {"identifier": "dup-1"}},
        headers=ADMIN_HEADERS,
    )
    assert first.status_code == 201, first.text
    dup = client.post(
        "/entity-records",
        json={"entity_type_id": et_id, "data": {"identifier": "dup-1"}},
        headers=ADMIN_HEADERS,
    )
    assert dup.status_code == 400, dup.text
