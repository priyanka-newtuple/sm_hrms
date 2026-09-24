"""Linking Field Library fields to forms, pinned to a version.

A link is a pin: the form reads the version it linked, so editing the field
afterwards cannot change a form underneath it. The cases worth holding down are
the ones where that pin could slip, or point somewhere it shouldn't.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import text

from entities.db_models import EntitiesModelService
from entities.manager import EntitiesServiceManager
from entities.models.request import (
    EntityRecordCreateRequest,
    EntityRecordUpdateRequest,
    EntityTypeCreateRequest,
)
from exceptions import NotFoundError, ValidationError
from field_library.db_models import FieldLibraryModelService, FormFieldLinkModelService
from field_library.manager import FieldLibraryServiceManager
from field_library.models.request import (
    FieldCreateRequest,
    FieldVersionCreateRequest,
    FormFieldLinkCreateRequest,
    FormFieldLinkRepinRequest,
)
from forms.db_models import (
    EntityTypeSchemaModel,
    FormsModelService,
    active_schema_fields,
)
from roles.db_models import RolesModelService

ORG_A = "test-org-1"
ORG_B = "test-org-2"
ACTOR_A = {"user_id": "user-a", "organization_id": ORG_A}
ACTOR_B = {"user_id": "user-b", "organization_id": ORG_B}
DEFS = "modular_backend_definitions"


@pytest.fixture
def db_service(entities_db_service_manager) -> FieldLibraryModelService:
    return FieldLibraryModelService(entities_db_service_manager)


@pytest.fixture
def link_service(entities_db_service_manager) -> FormFieldLinkModelService:
    return FormFieldLinkModelService(entities_db_service_manager)


@pytest.fixture
def manager(db_service, link_service) -> FieldLibraryServiceManager:
    service = FieldLibraryServiceManager(
        db_service, form_field_link_db_model_service=link_service
    )
    service.start()
    return service


@pytest.fixture
def session(entities_db_service_manager):
    db = entities_db_service_manager.postgres_db_service().get_db_session()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def clean_rows(session):
    """Purge both orgs' links, fields and forms, children before parents."""

    def _purge() -> None:
        session.execute(
            text(
                "DELETE FROM modular_backend_runtime.entities "
                "WHERE organization_id = ANY(:orgs)"
            ),
            {"orgs": [ORG_A, ORG_B]},
        )
        for table in (
            "entity_type_schema_fields",
            "field_library_field_versions",
            "field_library_fields",
            "entity_type_schema",
            "entity_types",
        ):
            session.execute(
                text(f"DELETE FROM {DEFS}.{table} WHERE organization_id = ANY(:orgs)"),
                {"orgs": [ORG_A, ORG_B]},
            )
        session.commit()

    _purge()
    yield
    _purge()


def _form(session, *, org: str = ORG_A, name: str = "Intake") -> str:
    schema_id = str(uuid.uuid4())
    session.add(
        EntityTypeSchemaModel(
            id=schema_id,
            organization_id=org,
            schema_key=f"key_{uuid.uuid4().hex[:8]}",
            name=name,
            entity_type="link_entity",
            fields_json=[],
            is_active=True,
        )
    )
    session.commit()
    return schema_id


def _field(manager, actor=ACTOR_A, **overrides):
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "name": f"Volume {suffix}",
        "field_key": f"volume_{suffix}",
        "field_type": "integer",
        "description": "millilitres",
        "settings": {"unit": "mL"},
    }
    payload.update(overrides)
    return manager.create_field_for_actor(actor, FieldCreateRequest(**payload))


def _link(manager, schema_id, field_id, *, actor=ACTOR_A, **overrides):
    payload = {"schema_id": schema_id, "library_field_id": field_id}
    payload.update(overrides)
    return manager.create_link_for_actor(actor, FormFieldLinkCreateRequest(**payload))


# ── Creating a link ───────────────────────────────────────────────────────────


def test_a_link_created_without_a_version_pins_the_current_one(manager, session) -> None:
    """Omitting the version means "as it stands now", resolved once."""
    schema_id = _form(session)
    created = _field(manager)
    second = manager.create_version_for_actor(
        ACTOR_A,
        created.identity.library_field_id,
        FieldVersionCreateRequest(settings={"unit": "L"}),
    )

    placement = _link(manager, schema_id, created.identity.library_field_id)

    assert placement.link.version_id == second.version_id, "the latest, not version 1"
    assert placement.version.version == 2
    assert placement.identity.library_field_id == created.identity.library_field_id


def test_a_link_created_with_an_explicit_version_pins_that_one(manager, session) -> None:
    schema_id = _form(session)
    created = _field(manager)
    field_id = created.identity.library_field_id
    manager.create_version_for_actor(
        ACTOR_A, field_id, FieldVersionCreateRequest(settings={"unit": "L"})
    )

    placement = _link(manager, schema_id, field_id, version_id=created.version.version_id)

    assert placement.link.version_id == created.version.version_id
    assert placement.version.version == 1, "an older version can be pinned deliberately"


def test_a_linked_document_is_projected_into_every_schema_reader(manager, session) -> None:
    schema_id = _form(session)
    created = _field(
        manager,
        name="Supporting documents",
        field_key="supporting_documents",
        field_type="document",
        settings={"required": True, "nullable": False},
    )

    _link(manager, schema_id, created.identity.library_field_id)
    session.expire_all()

    schema = session.get(EntityTypeSchemaModel, schema_id)
    assert schema.fields_json == [
        {
            "field": "supporting_documents",
            "name": "Supporting documents",
            "label": "Supporting documents",
            "type": "document",
            "description": "millilitres",
            "required": True,
            "nullable": False,
            "library_field_id": created.identity.library_field_id,
            "field_version_id": created.version.version_id,
        }
    ]
    assert active_schema_fields(session, ORG_A, "link_entity")[0]["type"] == "document"
    form_contract = FormsModelService().get_form_entity_schema(
        session, organization_id=ORG_A, schema_key=schema.schema_key
    )
    assert form_contract.fields[0].field == "supporting_documents"
    assert form_contract.fields[0].type == "document"
    assert RolesModelService().entity_field_exists(
        session, ORG_A, "link_entity", "supporting_documents"
    )


def test_linked_document_projection_drives_entity_create_and_update_validation(
    manager, session, entities_db_service_manager
) -> None:
    schema_id = _form(session)
    created = _field(
        manager,
        name="Reports",
        field_key="reports",
        field_type="document",
    )
    _link(manager, schema_id, created.identity.library_field_id)
    entities_db = EntitiesModelService(entities_db_service_manager)
    entity_type = entities_db.create_entity_type(
        EntityTypeCreateRequest(organization_id=ORG_A, name="link_entity")
    )
    entities = EntitiesServiceManager(
        entities_db, database_service_manager=entities_db_service_manager, config=None
    )
    filehandler = Mock()

    def _get_file(organization_id, file_id, owner_entity_id=None):
        if organization_id != ORG_A or file_id != "file-1":
            raise NotFoundError("file not found")
        return SimpleNamespace(file_id=file_id)

    filehandler.get_file.side_effect = _get_file
    entities.filehandler_service_manager = filehandler

    record = entities.create_entity_record(
        EntityRecordCreateRequest(
            organization_id=ORG_A,
            entity_type_id=entity_type.entity_type_id,
            data={"reports": ["file-1"]},
        )
    )
    assert record.data["reports"] == ["file-1"]

    with pytest.raises(ValidationError, match=r"reports.*missing.*does not exist"):
        entities.update_entity_record(
            organization_id=ORG_A,
            entity_id=record.entity_id,
            request=EntityRecordUpdateRequest(data={"reports": ["missing"]}),
        )
    unchanged = entities.get_entity_record(
        organization_id=ORG_A, entity_id=record.entity_id
    )
    assert unchanged.data["reports"] == ["file-1"]


def test_a_linked_timer_is_projected_into_every_schema_reader(manager, session) -> None:
    schema_id = _form(session)
    created = _field(
        manager,
        name="Elapsed time",
        field_key="elapsed_seconds",
        field_type="timer_duration",
        settings={"required": True, "nullable": False},
    )

    _link(manager, schema_id, created.identity.library_field_id)
    session.expire_all()

    schema = session.get(EntityTypeSchemaModel, schema_id)
    assert schema.fields_json == [
        {
            "field": "elapsed_seconds",
            "name": "Elapsed time",
            "label": "Elapsed time",
            "type": "timer_duration",
            "description": "millilitres",
            "required": True,
            "nullable": False,
            "library_field_id": created.identity.library_field_id,
            "field_version_id": created.version.version_id,
        }
    ]
    assert active_schema_fields(session, ORG_A, "link_entity")[0]["type"] == "timer_duration"
    form_contract = FormsModelService().get_form_entity_schema(
        session, organization_id=ORG_A, schema_key=schema.schema_key
    )
    assert form_contract.fields[0].field == "elapsed_seconds"
    assert form_contract.fields[0].type == "timer_duration"
    assert RolesModelService().entity_field_exists(
        session, ORG_A, "link_entity", "elapsed_seconds"
    )


def test_a_pin_does_not_move_when_the_field_gains_a_version(manager, session) -> None:
    """The point of pinning: a later edit cannot change a form underneath it."""
    schema_id = _form(session)
    created = _field(manager)
    field_id = created.identity.library_field_id
    _link(manager, schema_id, field_id)

    manager.create_version_for_actor(
        ACTOR_A, field_id, FieldVersionCreateRequest(settings={"unit": "L"})
    )

    listed = manager.list_links_for_actor(ACTOR_A, schema_id)
    assert [item.version.version for item in listed] == [1]
    assert listed[0].version.settings == {"unit": "mL"}


def test_the_same_field_cannot_be_linked_to_one_form_twice(manager, session) -> None:
    """Rejected cleanly, not as an integrity failure."""
    schema_id = _form(session)
    field_id = _field(manager).identity.library_field_id
    _link(manager, schema_id, field_id)

    with pytest.raises(ValidationError, match="already uses that field"):
        _link(manager, schema_id, field_id)

    assert len(manager.list_links_for_actor(ACTOR_A, schema_id)) == 1


def test_a_version_of_another_field_cannot_be_pinned(manager, session) -> None:
    schema_id = _form(session)
    ours = _field(manager)
    theirs = _field(manager)

    with pytest.raises(ValidationError, match="does not belong to field"):
        _link(
            manager,
            schema_id,
            ours.identity.library_field_id,
            version_id=theirs.version.version_id,
        )


def test_an_unknown_form_is_rejected(manager) -> None:
    field_id = _field(manager).identity.library_field_id
    with pytest.raises(NotFoundError, match="form"):
        _link(manager, str(uuid.uuid4()), field_id)


def test_an_unknown_field_is_rejected(manager, session) -> None:
    schema_id = _form(session)
    with pytest.raises(NotFoundError, match="field"):
        _link(manager, schema_id, str(uuid.uuid4()))


# ── Listing a form's fields ───────────────────────────────────────────────────


def test_a_form_lists_its_fields_in_position_order(manager, session) -> None:
    schema_id = _form(session)
    first = _field(manager).identity.library_field_id
    second = _field(manager).identity.library_field_id
    third = _field(manager).identity.library_field_id
    _link(manager, schema_id, second, position=1)
    _link(manager, schema_id, third, position=2)
    _link(manager, schema_id, first, position=0)

    listed = manager.list_links_for_actor(ACTOR_A, schema_id)

    assert [item.link.library_field_id for item in listed] == [first, second, third]
    assert [item.link.position for item in listed] == [0, 1, 2]


def test_each_listed_field_carries_its_identity_and_pinned_version(
    manager, session
) -> None:
    schema_id = _form(session)
    created = _field(manager, name="Batch Volume", field_key="batch_volume")
    _link(manager, schema_id, created.identity.library_field_id)

    item = manager.list_links_for_actor(ACTOR_A, schema_id)[0]

    assert item.identity.name == "Batch Volume"
    assert item.identity.field_key == "batch_volume"
    assert item.version.version_id == created.version.version_id
    assert item.version.settings == {"unit": "mL"}


def test_one_form_never_shows_another_forms_fields(manager, session) -> None:
    ours = _form(session, name="Ours")
    theirs = _form(session, name="Theirs")
    _link(manager, ours, _field(manager).identity.library_field_id)
    _link(manager, theirs, _field(manager).identity.library_field_id)

    assert len(manager.list_links_for_actor(ACTOR_A, ours)) == 1
    assert len(manager.list_links_for_actor(ACTOR_A, theirs)) == 1


# ── Repinning ─────────────────────────────────────────────────────────────────


def test_repinning_moves_the_form_to_another_version_of_the_same_field(
    manager, session
) -> None:
    schema_id = _form(session)
    created = _field(manager)
    field_id = created.identity.library_field_id
    placement = _link(manager, schema_id, field_id, version_id=created.version.version_id)
    second = manager.create_version_for_actor(
        ACTOR_A, field_id, FieldVersionCreateRequest(settings={"unit": "L"})
    )

    repinned = manager.repin_link_for_actor(
        ACTOR_A, placement.link.id, FormFieldLinkRepinRequest(version_id=second.version_id)
    )

    assert repinned.link.version_id == second.version_id
    listed = manager.list_links_for_actor(ACTOR_A, schema_id)
    assert [item.version.version for item in listed] == [2]
    assert listed[0].version.settings == {"unit": "L"}


def test_repinning_refreshes_the_authoritative_schema_projection(manager, session) -> None:
    schema_id = _form(session)
    created = _field(manager, settings={"required": False})
    placement = _link(manager, schema_id, created.identity.library_field_id)
    second = manager.create_version_for_actor(
        ACTOR_A,
        created.identity.library_field_id,
        FieldVersionCreateRequest(
            description="new description",
            settings={"required": True},
        ),
    )

    manager.repin_link_for_actor(
        ACTOR_A, placement.link.id, FormFieldLinkRepinRequest(version_id=second.version_id)
    )
    session.expire_all()

    projected = session.get(EntityTypeSchemaModel, schema_id).fields_json[0]
    assert projected["name"] == created.identity.name
    assert projected["description"] == "new description"
    assert projected["required"] is True
    assert projected["field_version_id"] == second.version_id


def test_repinning_to_a_version_of_a_different_field_is_rejected(manager, session) -> None:
    schema_id = _form(session)
    ours = _field(manager)
    theirs = _field(manager)
    placement = _link(manager, schema_id, ours.identity.library_field_id)

    with pytest.raises(ValidationError, match="does not belong to field"):
        manager.repin_link_for_actor(
            ACTOR_A,
            placement.link.id,
            FormFieldLinkRepinRequest(version_id=theirs.version.version_id),
        )

    listed = manager.list_links_for_actor(ACTOR_A, schema_id)
    assert listed[0].link.version_id == ours.version.version_id, "the pin did not move"


def test_repinning_an_unknown_link_is_rejected(manager) -> None:
    with pytest.raises(NotFoundError):
        manager.repin_link_for_actor(
            ACTOR_A, str(uuid.uuid4()), FormFieldLinkRepinRequest(version_id=str(uuid.uuid4()))
        )


# ── Unlinking ─────────────────────────────────────────────────────────────────


def test_unlinking_removes_the_row_and_leaves_the_field_alone(manager, session) -> None:
    """A link is a join, so removing it must never touch what it joined."""
    first_form = _form(session, name="First")
    second_form = _form(session, name="Second")
    created = _field(manager)
    field_id = created.identity.library_field_id
    placement = _link(manager, first_form, field_id)
    _link(manager, second_form, field_id)

    manager.delete_link_for_actor(ACTOR_A, placement.link.id)

    assert manager.list_links_for_actor(ACTOR_A, first_form) == []
    still_there = manager.list_links_for_actor(ACTOR_A, second_form)
    assert [item.link.library_field_id for item in still_there] == [field_id]
    assert manager.get_field_for_actor(ACTOR_A, field_id).identity.library_field_id == field_id
    assert len(manager.list_versions_for_actor(ACTOR_A, field_id)) == 1


def test_unlinking_removes_the_authoritative_schema_projection(manager, session) -> None:
    schema_id = _form(session)
    created = _field(manager)
    placement = _link(manager, schema_id, created.identity.library_field_id)

    manager.delete_link_for_actor(ACTOR_A, placement.link.id)
    session.expire_all()

    assert session.get(EntityTypeSchemaModel, schema_id).fields_json == []


def test_a_later_form_update_preserves_linked_field_projections(manager, session) -> None:
    schema_id = _form(session)
    created = _field(manager, field_key="linked_volume")
    _link(manager, schema_id, created.identity.library_field_id)
    forms = FormsModelService()

    forms.update_form_entity_schema(
        session,
        organization_id=ORG_A,
        schema_key=session.get(EntityTypeSchemaModel, schema_id).schema_key,
        name="Updated Intake",
        description=None,
        entity_type="link_entity",
        fields=[{"field": "notes", "type": "text"}],
        is_active=True,
        content_hash="caller-hash-is-recomputed",
    )
    session.expire_all()

    fields = session.get(EntityTypeSchemaModel, schema_id).fields_json
    assert [field["field"] for field in fields] == ["linked_volume", "notes"]
    assert fields[0]["library_field_id"] == created.identity.library_field_id


def test_unlinking_an_unknown_link_is_rejected(manager) -> None:
    with pytest.raises(NotFoundError):
        manager.delete_link_for_actor(ACTOR_A, str(uuid.uuid4()))


def test_a_field_can_be_relinked_after_being_unlinked(manager, session) -> None:
    schema_id = _form(session)
    field_id = _field(manager).identity.library_field_id
    placement = _link(manager, schema_id, field_id)
    manager.delete_link_for_actor(ACTOR_A, placement.link.id)

    relinked = _link(manager, schema_id, field_id)

    assert relinked.link.library_field_id == field_id


# ── Cross-organization isolation ──────────────────────────────────────────────


def test_another_org_cannot_link_a_field_to_our_form(manager, session) -> None:
    schema_id = _form(session, org=ORG_A)
    field_id = _field(manager).identity.library_field_id
    with pytest.raises(NotFoundError):
        _link(manager, schema_id, field_id, actor=ACTOR_B)


def test_a_form_cannot_link_a_field_from_another_org(manager, session) -> None:
    schema_id = _form(session, org=ORG_B)
    ours = _field(manager, actor=ACTOR_A).identity.library_field_id
    with pytest.raises(NotFoundError):
        _link(manager, schema_id, ours, actor=ACTOR_B)


def test_another_org_cannot_list_our_forms_fields(manager, session) -> None:
    schema_id = _form(session, org=ORG_A)
    _link(manager, schema_id, _field(manager).identity.library_field_id)
    with pytest.raises(NotFoundError):
        manager.list_links_for_actor(ACTOR_B, schema_id)


def test_another_org_cannot_repin_or_unlink_our_link(manager, session) -> None:
    schema_id = _form(session, org=ORG_A)
    created = _field(manager)
    placement = _link(manager, schema_id, created.identity.library_field_id)

    with pytest.raises(NotFoundError):
        manager.repin_link_for_actor(
            ACTOR_B,
            placement.link.id,
            FormFieldLinkRepinRequest(version_id=created.version.version_id),
        )
    with pytest.raises(NotFoundError):
        manager.delete_link_for_actor(ACTOR_B, placement.link.id)

    assert len(manager.list_links_for_actor(ACTOR_A, schema_id)) == 1
