from __future__ import annotations

import os
import socket
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock
from urllib.parse import urlparse

import pytest

from exceptions import ConflictError, NotFoundError, ValidationError
from forms.manager import FormsServiceManager
from forms.models.interface import PicklistContract, PicklistOption
from forms.models.request import PicklistCreateRequest, PicklistUpdateRequest


def _make_manager(
    fake_db_service: Any = None,
    workflow_manager: Any = None,
) -> FormsServiceManager:
    config = MagicMock()

    manager = FormsServiceManager.__new__(FormsServiceManager)
    manager.config = config
    manager.forms_db_model_service = fake_db_service or MagicMock()
    manager.workflow_service_manager = workflow_manager
    manager._entities_manager = None
    manager.module_name = "forms"
    manager._started = False
    return manager


def _pending_payload(
    entity_id: str = "entity-1", timeout_delta: timedelta = timedelta(hours=72)
) -> dict:
    return {
        "run_id": "run-1",
        "organization_id": "org-1",
        "entity_id": entity_id,
        "status": "pending_external",
        "external_timeout_at": datetime.now(UTC) + timeout_delta,
        "form": {"entity_type": "ATS.Application", "fields": []},
        "config": {},
    }


# ── get_public_form_by_entity Tests ───────────────────────────────────────────


def test_get_public_form_by_entity_returns_payload() -> None:
    fake_db = MagicMock()
    fake_db.get_public_form_by_entity.return_value = _pending_payload()
    manager = _make_manager(fake_db)

    result = manager.get_public_form_by_entity(object(), "entity-1")

    assert result["run_id"] == "run-1"
    assert result["entity_id"] == "entity-1"
    assert result["status"] == "pending_external"


def test_get_public_form_by_entity_raises_not_found_when_no_run() -> None:
    fake_db = MagicMock()
    fake_db.get_public_form_by_entity.return_value = None
    manager = _make_manager(fake_db)

    with pytest.raises(NotFoundError, match="no active form found"):
        manager.get_public_form_by_entity(object(), "entity-missing")


def test_get_public_form_by_entity_raises_when_already_completed() -> None:
    fake_db = MagicMock()
    payload = _pending_payload()
    payload["status"] = "succeeded"
    fake_db.get_public_form_by_entity.return_value = payload
    manager = _make_manager(fake_db)

    with pytest.raises(ValidationError, match="form has already been completed"):
        manager.get_public_form_by_entity(object(), "entity-1")


def test_get_public_form_by_entity_raises_when_expired() -> None:
    fake_db = MagicMock()
    payload = _pending_payload(timeout_delta=timedelta(hours=-1))
    fake_db.get_public_form_by_entity.return_value = payload
    manager = _make_manager(fake_db)

    with pytest.raises(ValidationError, match="form link has expired"):
        manager.get_public_form_by_entity(object(), "entity-1")


def test_get_public_form_by_entity_raises_when_blank_entity_id() -> None:
    manager = _make_manager()

    with pytest.raises(ValidationError, match="entity_id is required"):
        manager.get_public_form_by_entity(object(), "   ")


# ── submit_public_form_by_entity Tests ────────────────────────────────────────


def test_submit_public_form_returns_success() -> None:
    fake_db = MagicMock()
    fake_db.get_public_form_by_entity.return_value = {
        **_pending_payload(),
        "config": {"outcome_triggers": {"received": "advance"}},
    }
    fake_db.submit_public_form.return_value = {"created_entity_id": None}

    workflow = MagicMock()
    manager = _make_manager(fake_db, workflow_manager=workflow)

    result = manager.submit_public_form_by_entity(object(), "entity-1", {"name": "John"})

    assert result["success"] is True
    assert result["run_id"] == "run-1"
    assert result["entity_id"] == "entity-1"
    workflow.execute_transition_system.assert_called_once_with(
        organization_id="org-1",
        entity_id="entity-1",
        trigger="advance",
    )


def test_submit_public_form_skips_trigger_when_none_configured() -> None:
    fake_db = MagicMock()
    fake_db.get_public_form_by_entity.return_value = {
        **_pending_payload(),
        "config": {"outcome_triggers": {}},
    }
    fake_db.submit_public_form.return_value = {"created_entity_id": None}

    workflow = MagicMock()
    manager = _make_manager(fake_db, workflow_manager=workflow)
    result = manager.submit_public_form_by_entity(object(), "entity-1", {"name": "John"})

    assert result["success"] is True
    workflow.execute_transition_system.assert_not_called()


# ── Picklist DB integration tests ─────────────────────────────────────────────

_PICKLIST_TEST_ORG = "test-org-1"


def _db_is_reachable() -> bool:
    url = (
        os.environ.get("DATABASE_URL")
        or "postgresql://statemachine:statemachine@modular-db:5432/statemachine"
    )
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    try:
        socket.getaddrinfo(host, port)
    except OSError:
        return False
    return True


@pytest.fixture
def forms_db_service(entities_db_service_manager):
    """FormsModelService wired to the real Postgres test DB.

    Cleans picklist rows for the test org before and after each test so
    tests are isolated without needing to roll back transactions.
    """
    from sqlalchemy import text

    from forms.db_models import FormsModelService

    engine = entities_db_service_manager.postgres_db_service().engine
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "modular_backend")
    definitions_schema = f"{app_schema}_definitions"

    def _cleanup() -> None:
        with engine.begin() as conn:
            conn.execute(
                text(f'DELETE FROM "{app_schema}".picklists WHERE organization_id = :org'),
                {"org": _PICKLIST_TEST_ORG},
            )
            conn.execute(
                text(
                    f'DELETE FROM "{definitions_schema}".entity_type_schema '
                    "WHERE organization_id = :org"
                ),
                {"org": _PICKLIST_TEST_ORG},
            )

    _cleanup()
    service = FormsModelService(database_service_manager=entities_db_service_manager)
    yield service
    _cleanup()


@pytest.mark.skipif(not _db_is_reachable(), reason="Postgres host is not reachable in this environment")
def test_picklist_create_and_list(forms_db_service) -> None:
    svc = forms_db_service
    db = svc.database_service_manager.postgres_db_service().get_db_session()
    try:
        req = PicklistCreateRequest(
            name="Source",
            options=[PicklistOption(value="linkedin", label="LinkedIn")],
        )
        created = svc.create_picklist(db, _PICKLIST_TEST_ORG, req)

        assert created.name == "Source"
        assert created.id is not None
        assert len(created.options) == 1

        items = svc.list_picklists(db, _PICKLIST_TEST_ORG)
        assert len(items) == 1
        assert items[0].name == "Source"
    finally:
        db.close()


@pytest.mark.skipif(not _db_is_reachable(), reason="Postgres host is not reachable in this environment")
def test_picklist_list_returns_empty_when_none(forms_db_service) -> None:
    svc = forms_db_service
    db = svc.database_service_manager.postgres_db_service().get_db_session()
    try:
        items = svc.list_picklists(db, _PICKLIST_TEST_ORG)
        assert items == []
    finally:
        db.close()


@pytest.mark.skipif(not _db_is_reachable(), reason="Postgres host is not reachable in this environment")
def test_picklist_get_returns_row(forms_db_service) -> None:
    svc = forms_db_service
    db = svc.database_service_manager.postgres_db_service().get_db_session()
    try:
        req = PicklistCreateRequest(name="Stage", options=[])
        created = svc.create_picklist(db, _PICKLIST_TEST_ORG, req)

        fetched = svc.get_picklist(db, _PICKLIST_TEST_ORG, created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.name == "Stage"
    finally:
        db.close()


@pytest.mark.skipif(not _db_is_reachable(), reason="Postgres host is not reachable in this environment")
def test_picklist_get_returns_none_for_missing(forms_db_service) -> None:
    svc = forms_db_service
    db = svc.database_service_manager.postgres_db_service().get_db_session()
    try:
        result = svc.get_picklist(db, _PICKLIST_TEST_ORG, "does-not-exist")
        assert result is None
    finally:
        db.close()


@pytest.mark.skipif(not _db_is_reachable(), reason="Postgres host is not reachable in this environment")
def test_picklist_update_changes_name_and_options(forms_db_service) -> None:
    svc = forms_db_service
    db = svc.database_service_manager.postgres_db_service().get_db_session()
    try:
        req = PicklistCreateRequest(name="Old Name", options=[])
        created = svc.create_picklist(db, _PICKLIST_TEST_ORG, req)

        update_req = PicklistUpdateRequest(
            name="New Name",
            options=[PicklistOption(value="opt1", label="Option 1")],
        )
        updated = svc.update_picklist(db, _PICKLIST_TEST_ORG, created.id, update_req)

        assert updated is not None
        assert updated.name == "New Name"
        assert len(updated.options) == 1
    finally:
        db.close()


@pytest.mark.skipif(not _db_is_reachable(), reason="Postgres host is not reachable in this environment")
def test_picklist_update_returns_none_for_missing(forms_db_service) -> None:
    svc = forms_db_service
    db = svc.database_service_manager.postgres_db_service().get_db_session()
    try:
        result = svc.update_picklist(
            db, _PICKLIST_TEST_ORG, "does-not-exist", PicklistUpdateRequest(name="X")
        )
        assert result is None
    finally:
        db.close()


@pytest.mark.skipif(not _db_is_reachable(), reason="Postgres host is not reachable in this environment")
def test_picklist_soft_delete_hides_from_list(forms_db_service) -> None:
    """Deleted picklist must not appear in list or get, but must still exist in DB."""
    svc = forms_db_service
    db = svc.database_service_manager.postgres_db_service().get_db_session()
    try:
        req = PicklistCreateRequest(name="ToDelete", options=[])
        created = svc.create_picklist(db, _PICKLIST_TEST_ORG, req)

        deleted = svc.delete_picklist(db, _PICKLIST_TEST_ORG, created.id)
        assert deleted is True

        assert svc.get_picklist(db, _PICKLIST_TEST_ORG, created.id) is None
        items = svc.list_picklists(db, _PICKLIST_TEST_ORG)
        assert all(item.id != created.id for item in items)
    finally:
        db.close()


@pytest.mark.skipif(not _db_is_reachable(), reason="Postgres host is not reachable in this environment")
def test_picklist_delete_returns_false_for_missing(forms_db_service) -> None:
    svc = forms_db_service
    db = svc.database_service_manager.postgres_db_service().get_db_session()
    try:
        result = svc.delete_picklist(db, _PICKLIST_TEST_ORG, "does-not-exist")
        assert result is False
    finally:
        db.close()


@pytest.mark.skipif(not _db_is_reachable(), reason="Postgres host is not reachable in this environment")
def test_picklist_create_same_name_after_archive(forms_db_service) -> None:
    """Archived picklist must not block creation of a new one with the same name.

    This is the partial unique index regression: the old full constraint on
    (organization_id, name) would raise a duplicate key error even after the
    first picklist was soft-deleted. The new partial index only enforces
    uniqueness when archived_at IS NULL.
    """
    svc = forms_db_service
    db = svc.database_service_manager.postgres_db_service().get_db_session()
    try:
        req = PicklistCreateRequest(name="Source", options=[])
        first = svc.create_picklist(db, _PICKLIST_TEST_ORG, req)
        svc.delete_picklist(db, _PICKLIST_TEST_ORG, first.id)

        second = svc.create_picklist(db, _PICKLIST_TEST_ORG, PicklistCreateRequest(name="Source", options=[]))

        assert second.name == "Source"
        assert second.id != first.id

        items = svc.list_picklists(db, _PICKLIST_TEST_ORG)
        assert len(items) == 1
        assert items[0].id == second.id
    finally:
        db.close()


@pytest.mark.skipif(not _db_is_reachable(), reason="Postgres host is not reachable in this environment")
def test_picklist_duplicate_name_raises_conflict(forms_db_service) -> None:
    """Creating two active picklists with the same name must raise ConflictError."""
    svc = forms_db_service
    db = svc.database_service_manager.postgres_db_service().get_db_session()
    try:
        svc.create_picklist(db, _PICKLIST_TEST_ORG, PicklistCreateRequest(name="Source", options=[]))

        with pytest.raises(ConflictError, match="already exists"):
            svc.create_picklist(db, _PICKLIST_TEST_ORG, PicklistCreateRequest(name="Source", options=[]))
    finally:
        db.close()


# ── Entity type schema (multi-form) Tests ─────────────────────────────────────


def _create_schema(svc, db, *, schema_key: str, entity_type: str, display_order: int = 0):
    """Helper to insert one entity type schema row for the test org."""
    return svc.create_form_entity_schema(
        db,
        organization_id=_PICKLIST_TEST_ORG,
        schema_key=schema_key,
        name=schema_key,
        description=None,
        entity_type=entity_type,
        fields=[],
        is_active=True,
        content_hash=schema_key,
        display_order=display_order,
    )


@pytest.mark.skipif(not _db_is_reachable(), reason="Postgres host is not reachable in this environment")
def test_multiple_schemas_attach_to_one_entity_type(forms_db_service) -> None:
    """Several forms may share an entity type; list returns all of them."""
    svc = forms_db_service
    db = svc.database_service_manager.postgres_db_service().get_db_session()
    try:
        _create_schema(svc, db, schema_key="candidate__a", entity_type="Candidate")
        _create_schema(svc, db, schema_key="candidate__b", entity_type="Candidate")

        items = svc.list_form_entity_schemas(
            organization_id=_PICKLIST_TEST_ORG, entity_type="Candidate"
        )
        assert {s.schema_key for s in items} == {"candidate__a", "candidate__b"}
    finally:
        db.close()


@pytest.mark.skipif(not _db_is_reachable(), reason="Postgres host is not reachable in this environment")
def test_schemas_ordered_by_display_order_then_key(forms_db_service) -> None:
    """List orders by display_order ascending, with schema_key as the tiebreaker."""
    svc = forms_db_service
    db = svc.database_service_manager.postgres_db_service().get_db_session()
    try:
        _create_schema(svc, db, schema_key="candidate__z", entity_type="Candidate", display_order=1)
        _create_schema(svc, db, schema_key="candidate__a", entity_type="Candidate", display_order=2)
        _create_schema(svc, db, schema_key="candidate__m", entity_type="Candidate", display_order=1)

        items = svc.list_form_entity_schemas(
            organization_id=_PICKLIST_TEST_ORG, entity_type="Candidate"
        )
        # display_order 1 group first (m, z by key), then display_order 2 (a).
        assert [s.schema_key for s in items] == [
            "candidate__m",
            "candidate__z",
            "candidate__a",
        ]
    finally:
        db.close()


@pytest.mark.skipif(not _db_is_reachable(), reason="Postgres host is not reachable in this environment")
def test_manager_display_order_only_update_persists(forms_db_service) -> None:
    """A display_order-only update serializes carried-over fields (reorder regression).

    The fields are not in the payload, so they are reused from the stored row as
    contract objects; they must be JSON-serialized before hitting the JSONB column.
    """
    from forms.models.request import EntityTypeSchemaCreateRequest, EntityTypeSchemaUpdateRequest

    svc = forms_db_service
    manager = _make_manager(fake_db_service=svc)
    actor = {"organization_id": _PICKLIST_TEST_ORG}
    db = svc.database_service_manager.postgres_db_service().get_db_session()
    try:
        manager.create_form_entity_schema_for_actor(
            actor,
            EntityTypeSchemaCreateRequest(
                schema_key="candidate__basic",
                name="Basic",
                entity_type="Candidate",
                fields=[
                    {"field": "first_name", "type": "string", "required": True, "nullable": False}
                ],
                display_order=0,
            ),
            db,
        )
        updated = manager.update_form_entity_schema_for_actor(
            actor, db, "candidate__basic", EntityTypeSchemaUpdateRequest(display_order=5)
        )
        assert updated.display_order == 5
        assert [f.field for f in updated.fields] == ["first_name"]
    finally:
        db.close()


@pytest.mark.skipif(not _db_is_reachable(), reason="Postgres host is not reachable in this environment")
def test_strip_inherited_fields_ignores_inactive_forms(forms_db_service) -> None:
    """Inherited fields on an inactive form must not strip an editable field with
    the same id on the active form (regression for the multi-form union)."""
    from uuid import uuid4

    from entities.db_models import EntitiesModelService, EntityTypeModel

    svc = forms_db_service
    entity_svc = EntitiesModelService(svc.database_service_manager, forms_db_model_service=svc)
    db = svc.database_service_manager.postgres_db_service().get_db_session()
    type_id = str(uuid4())
    try:
        db.add(
            EntityTypeModel(
                entity_type_id=type_id, organization_id=_PICKLIST_TEST_ORG, name="Candidate"
            )
        )
        # Active form: "owner_name" is an ordinary editable field.
        svc.create_form_entity_schema(
            db,
            organization_id=_PICKLIST_TEST_ORG,
            schema_key="candidate__active",
            name="Active",
            description=None,
            entity_type="Candidate",
            fields=[{"field": "owner_name", "type": "string", "required": False, "nullable": True}],
            is_active=True,
            content_hash="active",
        )
        # Inactive form: same id, but declared as an inherited field.
        svc.create_form_entity_schema(
            db,
            organization_id=_PICKLIST_TEST_ORG,
            schema_key="candidate__inactive",
            name="Inactive",
            description=None,
            entity_type="Candidate",
            fields=[
                {
                    "field": "owner_name",
                    "type": "string",
                    "required": False,
                    "nullable": True,
                    "ownership": "inherited",
                    "source": {"context_entity_type": "Client", "context_field": "name"},
                }
            ],
            is_active=False,
            content_hash="inactive",
        )

        result = entity_svc.strip_inherited_fields(
            organization_id=_PICKLIST_TEST_ORG,
            entity_type_id=type_id,
            data={"owner_name": "typed by user"},
        )
        # The inactive form's inherited declaration is ignored, so the value stays.
        assert result == {"owner_name": "typed by user"}
    finally:
        db.query(EntityTypeModel).filter_by(entity_type_id=type_id).delete()
        db.commit()
        db.close()

@pytest.mark.skipif(not _db_is_reachable(), reason="Postgres host is not reachable in this environment")
def test_get_active_entity_schemas_returns_only_active_schemas(
    forms_db_service, entities_db_service_manager
) -> None:
    """The cross-module read used by the workflow module, against the real manager.

    The workflow module compares a workflow's saved entity_schema against the live form for its
    entity type. It has no actor and no request session, so it calls this rather than the
    actor-scoped listing. The `is_active` filter is policy and deliberately lives in the manager,
    so it needs asserting here rather than only through a double.
    """
    from forms.manager import FormsServiceManager

    svc = forms_db_service
    db = svc.database_service_manager.postgres_db_service().get_db_session()
    try:
        _create_schema(svc, db, schema_key="patient__live", entity_type="Patient")
        _create_schema(svc, db, schema_key="patient__old", entity_type="Patient")
        _create_schema(svc, db, schema_key="doctor__live", entity_type="Doctor")
        svc.update_form_entity_schema(
            db,
            organization_id=_PICKLIST_TEST_ORG,
            schema_key="patient__old",
            name="patient__old",
            description=None,
            entity_type="Patient",
            fields=[],
            is_active=False,
            content_hash="patient__old",
            display_order=0,
        )
    finally:
        db.close()

    manager = FormsServiceManager(
        svc, database_service_manager=entities_db_service_manager, config=None, roles_manager=None
    )

    patient = manager.get_active_entity_schemas(_PICKLIST_TEST_ORG, "Patient")
    assert [item.schema_key for item in patient] == ["patient__live"], (
        "the inactive schema must be filtered out"
    )
    assert all(item.is_active for item in patient)

    doctor = manager.get_active_entity_schemas(_PICKLIST_TEST_ORG, "Doctor")
    assert [item.schema_key for item in doctor] == ["doctor__live"], "scoped to one entity type"

    assert manager.get_active_entity_schemas(_PICKLIST_TEST_ORG, "Nurse") == [], (
        "an entity type with no form yields an empty list, which switches the drift check off"
    )
