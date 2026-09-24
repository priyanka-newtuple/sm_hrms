"""Pinning a Method's inherited field into a workflow.

A Method-field usage can carry `inherit_from` ("<EntityType>.<field>"),
meaning: at pin time, this field's value should come from a related record,
not be entered directly. Resolved only at publish, alongside the existing
method-field-conflict check, because publish is the only moment the
workflow's own entity type is known.

Three things must hold, in order: a relation must already exist from the
named source entity type to the workflow's own entity type (never
auto-created); the named source field must exist on that entity type's
active form today (catches typos and drift the relation check alone would
miss); and writing the mapping must never remap a source field something
else already maps to a different target (checked against both what's
already persisted and every other pin in the same publish).

Real Postgres throughout — the parts worth testing are exactly where a stub
would paper over the distinction: whether the relation and field really
exist right now, not merely at authoring time.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import text

from entities.db_models import EntitiesModelService
from entities.manager import EntitiesServiceManager
from entities.models.interface import RelationType
from entities.models.request import (
    EntityRelationDeclarationCreateRequest,
    EntityTypeCreateRequest,
)
from exceptions import ValidationError
from field_library.db_models import FieldLibraryModelService
from forms.db_models import FormsModelService
from forms.manager import FormsServiceManager
from method_library.db_models import MethodLibraryModelService
from method_library.models.request import MethodFieldInput
from workflow.db_models import WorkflowModelService
from workflow.manager import WorkflowServiceManager
from workflow.models import WorkflowPublishRequest
from workflow.models.interface import (
    EntitySchema,
    MethodRef,
    State,
    StateMachineDefinition,
    Transition,
)

ORG_A = "test-org-1"
ACTOR_A = {"organization_id": ORG_A, "user_id": "user-a", "roles": ["admin"]}
DEFINITIONS = "modular_backend_definitions"


@pytest.fixture
def entities_db(entities_db_service_manager) -> EntitiesModelService:
    return EntitiesModelService(entities_db_service_manager)


@pytest.fixture
def entities_service_manager(entities_db, entities_db_service_manager) -> EntitiesServiceManager:
    """The entities manager with an allow-everything roles manager.

    Not optional: every write path goes through `_check_entity_permission`,
    which calls `roles_manager.evaluate_entity_access` unconditionally for a
    non-system actor. These tests are about inheritance, not RBAC, so the
    permission layer is stubbed wide open — `test_inherited_field_rbac_matrix`
    is where the real gating is exercised.
    """
    roles = Mock()
    roles.evaluate_entity_access.return_value = SimpleNamespace(allowed=True, conditions=[])
    roles.get_visible_fields.return_value = None
    roles.get_editable_fields.return_value = None
    roles.get_masked_fields.return_value = set()
    roles.get_workflow_access_scope.return_value = None
    # Not None-by-accident: `resolve_read_policies` probes for this optional
    # batched resolver with getattr+callable, and a bare Mock would answer the
    # probe and then return a Mock instead of a policy dict. None makes the
    # manager take its per-type path, which the stubs above do cover.
    roles.resolve_entity_read_policies = None
    users = Mock()
    users.get_actor_display_info.return_value = (None, None)
    users.get_user_display_info.return_value = (None, None)
    return EntitiesServiceManager(
        entities_db,
        entities_db_service_manager,
        config=None,
        roles_manager=roles,
        audit_service_manager=Mock(),
        user_service_manager=users,
    )


@pytest.fixture
def forms_db(entities_db_service_manager) -> FormsServiceManager:
    """The forms SERVICE manager, which is what WorkflowServiceManager takes now.

    `main` wires the model service in behind it; the workflow manager only ever
    reaches forms through the service manager.
    """
    return FormsServiceManager(
        FormsModelService(entities_db_service_manager),
        entities_db_service_manager,
        None,
    )


@pytest.fixture
def field_service(entities_db_service_manager) -> FieldLibraryModelService:
    return FieldLibraryModelService(entities_db_service_manager)


@pytest.fixture
def method_service(entities_db_service_manager) -> MethodLibraryModelService:
    return MethodLibraryModelService(entities_db_service_manager)


@pytest.fixture
def workflow_db(entities_db_service_manager) -> WorkflowModelService:
    return WorkflowModelService(entities_db_service_manager)


@pytest.fixture
def manager(
    entities_db_service_manager, workflow_db, method_service, entities_service_manager, forms_db
) -> WorkflowServiceManager:
    roles = Mock()
    roles.get_workflow_access_scope.return_value = None
    return WorkflowServiceManager(
        workflow_db_model_service=workflow_db,
        database_service_manager=entities_db_service_manager,
        config=None,
        entities_service_manager=entities_service_manager,
        roles_manager=roles,
        audit_events_service=None,
        forms_service_manager=forms_db,
        method_library_db_model_service=method_service,
        filehandler_service_manager=None,
        user_service_manager=None,
        blob_storage_service=None,
    )


@pytest.fixture(autouse=True)
def clean_rows(entities_db_service_manager):
    """Purge every row this file's tests create, children before parents."""

    def _purge() -> None:
        session = entities_db_service_manager.postgres_db_service().get_db_session()
        try:
            for statement in (
                "DELETE FROM {definitions}.workflow_method_pins WHERE organization_id = :org",
                "DELETE FROM {app}.workflow_state_machines WHERE organization_id = :org",
                "DELETE FROM {definitions}.method_library_method_version_fields "
                "WHERE organization_id = :org",
                "DELETE FROM {definitions}.method_library_method_versions WHERE organization_id = :org",
                "DELETE FROM {definitions}.method_library_methods WHERE organization_id = :org",
                "DELETE FROM {definitions}.method_library_org_counters WHERE organization_id = :org",
                "DELETE FROM {definitions}.field_library_field_versions WHERE organization_id = :org",
                "DELETE FROM {definitions}.field_library_fields WHERE organization_id = :org",
                "DELETE FROM {definitions}.entity_type_schema WHERE organization_id = :org",
                "DELETE FROM {definitions}.entity_type_relations WHERE organization_id = :org",
                "DELETE FROM {definitions}.entity_types WHERE organization_id = :org",
            ):
                session.execute(
                    text(statement.format(definitions=DEFINITIONS, app="modular_backend")),
                    {"org": ORG_A},
                )
            session.commit()
        finally:
            session.close()

    _purge()
    yield
    _purge()


# ── Fixture builders ──────────────────────────────────────────────────────────


def _entity_type(entities_db, name: str) -> str:
    return entities_db.create_entity_type(
        EntityTypeCreateRequest(organization_id=ORG_A, name=name)
    ).entity_type_id


def _active_form(forms_db, entities_db_service_manager, entity_type_name: str, field_keys: list[str]):
    """`forms_db` is the forms SERVICE manager; the raw schema writer lives on
    the model service behind it."""
    session = entities_db_service_manager.postgres_db_service().get_db_session()
    try:
        forms_db.forms_db_model_service.create_form_entity_schema(
            session,
            organization_id=ORG_A,
            schema_key=f"form_{uuid.uuid4().hex[:8]}",
            name="Form",
            description=None,
            entity_type=entity_type_name,
            fields=[{"field": key, "type": "text"} for key in field_keys],
            is_active=True,
            content_hash=uuid.uuid4().hex,
        )
    finally:
        session.close()


def _declaration(entities_db, *, from_entity_type_id: str, to_entity_type_id: str) -> str:
    return entities_db.create_entity_relation_declaration(
        EntityRelationDeclarationCreateRequest(
            organization_id=ORG_A,
            from_entity_type_id=from_entity_type_id,
            to_entity_type_id=to_entity_type_id,
            relation_type=RelationType.REFERENCE,
        ),
        default_relation_type=RelationType.REFERENCE.value,
    ).relation_def_id


def _relation_metadata(entities_db_service_manager, relation_def_id: str) -> dict:
    session = entities_db_service_manager.postgres_db_service().get_db_session()
    try:
        row = session.execute(
            text(
                f"SELECT relation_metadata FROM {DEFINITIONS}.entity_type_relations "
                "WHERE relation_def_id = :id"
            ),
            {"id": relation_def_id},
        ).first()
        return dict(row[0]) if row is not None else {}
    finally:
        session.close()


def _make_field(field_service, *, field_type: str = "text") -> tuple[str, str]:
    suffix = uuid.uuid4().hex[:8]
    created = field_service.create_field(
        organization_id=ORG_A,
        name=f"Field {suffix}",
        field_key=f"field_{suffix}",
        field_type=field_type,
        description=None,
        settings={},
        created_by="user-a",
    )
    return created.identity.library_field_id, created.identity.field_key


def _make_method(method_service, *, name: str, fields: list[MethodFieldInput]):
    identity, version = method_service.create_method_with_fields(
        organization_id=ORG_A,
        name=name,
        description=None,
        category_id=None,
        field_inputs=fields,
        created_by="user-a",
    )
    return identity, version


def _input(library_field_id: str, *, inherit_from: str | None = None, position: int = 0):
    return MethodFieldInput(
        library_field_id=library_field_id,
        label="Field",
        placeholder="e.g. value",
        required=False,
        position=position,
        inherit_from=inherit_from,
    )


def _definition(entity_type: str, states: list[State]) -> StateMachineDefinition:
    return StateMachineDefinition(
        machine_key="inherited_field_machine",
        name="Inherited Field Machine",
        entity_type=entity_type,
        entity_schema=EntitySchema(entity_type=entity_type, fields=[]),
        states=states,
        initial_state="start",
        transitions=[
            Transition(
                key="start_to_end",
                trigger="complete",
                label="Complete",
                to_state="end",
                **{"from": "start"},
            )
        ],
    )


def _states(method_refs: list[MethodRef]) -> list[State]:
    return [
        State(name="start", tags=["initial"], order=1, method_refs=method_refs),
        State(name="end", tags=["terminal"], order=2),
    ]


def _draft(workflow_db, entity_type: str) -> str:
    record = workflow_db.create_state_machine_draft(
        organization_id=ORG_A,
        machine_name=f"inherited_{uuid.uuid4().hex[:8]}",
        machine_key="inherited_field_machine",
        definition=_definition(entity_type, _states([])).model_dump(mode="json"),
        created_by="user-a",
    )
    return record.id


def _publish(manager, row_id: str, definition: StateMachineDefinition):
    return manager.publish_workflow_for_actor(
        ACTOR_A, row_id, WorkflowPublishRequest(definition=definition)
    )


# ── No relation declared ──────────────────────────────────────────────────────


def test_publish_blocks_when_no_relation_is_declared(
    manager, workflow_db, method_service, field_service, entities_db
) -> None:
    target_name = f"Request_{uuid.uuid4().hex[:8]}"
    _entity_type(entities_db, target_name)
    field_id, _field_key = _make_field(field_service)
    identity, _version = _make_method(
        method_service,
        name="Client Lookup",
        fields=[_input(field_id, inherit_from=f"NoSuchClient_{uuid.uuid4().hex[:8]}.name")],
    )
    row_id = _draft(workflow_db, target_name)

    with pytest.raises(ValidationError, match="no relation is declared"):
        _publish(
            manager,
            row_id,
            _definition(target_name, _states([MethodRef(method_id=identity.method_id)])),
        )


def test_a_relation_to_a_different_type_does_not_satisfy_the_check(
    manager, workflow_db, method_service, field_service, entities_db
) -> None:
    """The relation must point at THIS workflow's entity type, not just exist somewhere."""
    source_name = f"Client_{uuid.uuid4().hex[:8]}"
    target_name = f"Request_{uuid.uuid4().hex[:8]}"
    source_type = _entity_type(entities_db, source_name)
    unrelated_type = _entity_type(entities_db, f"Unrelated_{uuid.uuid4().hex[:8]}")
    _entity_type(entities_db, target_name)
    _declaration(entities_db, from_entity_type_id=source_type, to_entity_type_id=unrelated_type)
    field_id, _field_key = _make_field(field_service)
    identity, _version = _make_method(
        method_service,
        name="Client Lookup",
        fields=[_input(field_id, inherit_from=f"{source_name}.name")],
    )
    row_id = _draft(workflow_db, target_name)

    with pytest.raises(ValidationError, match="no relation is declared"):
        _publish(
            manager,
            row_id,
            _definition(target_name, _states([MethodRef(method_id=identity.method_id)])),
        )


# ── Relation exists, field does not ───────────────────────────────────────────


def test_publish_blocks_when_the_source_field_does_not_exist(
    manager, workflow_db, method_service, field_service, entities_db, forms_db,
    entities_db_service_manager,
) -> None:
    source_name = f"Client_{uuid.uuid4().hex[:8]}"
    target_name = f"Request_{uuid.uuid4().hex[:8]}"
    source_type = _entity_type(entities_db, source_name)
    target_type = _entity_type(entities_db, target_name)
    _active_form(forms_db, entities_db_service_manager, source_name, ["name"])
    _declaration(entities_db, from_entity_type_id=source_type, to_entity_type_id=target_type)
    field_id, field_key = _make_field(field_service)
    identity, _version = _make_method(
        method_service,
        name="Client Lookup",
        fields=[_input(field_id, inherit_from=f"{source_name}.nmae")],  # typo, on purpose
    )
    row_id = _draft(workflow_db, target_name)

    with pytest.raises(ValidationError, match="not a field on"):
        _publish(
            manager,
            row_id,
            _definition(target_name, _states([MethodRef(method_id=identity.method_id)])),
        )


# ── The success path, and the write it produces ───────────────────────────────


def test_publish_succeeds_and_writes_the_mapping_matching_the_manual_flows_shape(
    manager, workflow_db, method_service, field_service, entities_db, forms_db,
    entities_db_service_manager,
) -> None:
    source_name = f"Client_{uuid.uuid4().hex[:8]}"
    target_name = f"Request_{uuid.uuid4().hex[:8]}"
    source_type = _entity_type(entities_db, source_name)
    target_type = _entity_type(entities_db, target_name)
    _active_form(forms_db, entities_db_service_manager, source_name, ["name"])
    relation_def_id = _declaration(
        entities_db, from_entity_type_id=source_type, to_entity_type_id=target_type
    )
    field_id, field_key = _make_field(field_service)
    identity, _version = _make_method(
        method_service,
        name="Client Lookup",
        fields=[_input(field_id, inherit_from=f"{source_name}.name")],
    )
    row_id = _draft(workflow_db, target_name)

    published = _publish(
        manager,
        row_id,
        _definition(target_name, _states([MethodRef(method_id=identity.method_id)])),
    )

    assert published.state_machine.version == 1
    # Matches the manual "Add from related entity" flow's own shape exactly:
    # key = "<Source>.<source_field>", value = "<Target>.<target_field>".
    assert _relation_metadata(entities_db_service_manager, relation_def_id) == {
        f"{source_name}.name": f"{target_name}.{field_key}",
    }


def test_republishing_with_the_same_mapping_is_not_a_conflict(
    manager, workflow_db, method_service, field_service, entities_db, forms_db,
    entities_db_service_manager,
) -> None:
    source_name = f"Client_{uuid.uuid4().hex[:8]}"
    target_name = f"Request_{uuid.uuid4().hex[:8]}"
    source_type = _entity_type(entities_db, source_name)
    target_type = _entity_type(entities_db, target_name)
    _active_form(forms_db, entities_db_service_manager, source_name, ["name"])
    relation_def_id = _declaration(
        entities_db, from_entity_type_id=source_type, to_entity_type_id=target_type
    )
    field_id, field_key = _make_field(field_service)
    identity, _version = _make_method(
        method_service,
        name="Client Lookup",
        fields=[_input(field_id, inherit_from=f"{source_name}.name")],
    )
    row_id = _draft(workflow_db, target_name)
    definition = _definition(target_name, _states([MethodRef(method_id=identity.method_id)]))
    _publish(manager, row_id, definition)

    # Republish the same draft row — `_draft` mints a fresh machine_name per
    # call, so a second draft would be a different machine and version 2
    # could never exist for it.
    published_again = _publish(manager, row_id, definition)

    assert published_again.state_machine.version == 2
    assert _relation_metadata(entities_db_service_manager, relation_def_id) == {
        f"{source_name}.name": f"{target_name}.{field_key}",
    }


# ── Remap conflicts ────────────────────────────────────────────────────────────


def test_publish_blocks_remapping_a_source_field_already_mapped_elsewhere(
    manager, workflow_db, method_service, field_service, entities_db, forms_db,
    entities_db_service_manager,
) -> None:
    source_name = f"Client_{uuid.uuid4().hex[:8]}"
    target_name = f"Request_{uuid.uuid4().hex[:8]}"
    source_type = _entity_type(entities_db, source_name)
    target_type = _entity_type(entities_db, target_name)
    _active_form(forms_db, entities_db_service_manager, source_name, ["name"])
    relation_def_id = _declaration(
        entities_db, from_entity_type_id=source_type, to_entity_type_id=target_type
    )
    first_field_id, first_field_key = _make_field(field_service)
    first_identity, _ = _make_method(
        method_service,
        name="First Mapper",
        fields=[_input(first_field_id, inherit_from=f"{source_name}.name")],
    )
    row_id = _draft(workflow_db, target_name)
    _publish(
        manager, row_id, _definition(target_name, _states([MethodRef(method_id=first_identity.method_id)]))
    )

    second_field_id, second_field_key = _make_field(field_service)
    second_identity, _ = _make_method(
        method_service,
        name="Second Mapper",
        fields=[_input(second_field_id, inherit_from=f"{source_name}.name")],
    )
    row_id_2 = _draft(workflow_db, target_name)

    with pytest.raises(ValidationError, match="already maps it to"):
        _publish(
            manager,
            row_id_2,
            _definition(target_name, _states([MethodRef(method_id=second_identity.method_id)])),
        )

    # The first mapping survives untouched.
    assert _relation_metadata(entities_db_service_manager, relation_def_id) == {
        f"{source_name}.name": f"{target_name}.{first_field_key}",
    }


def test_publish_blocks_two_pins_in_the_same_publish_disagreeing(
    manager, workflow_db, method_service, field_service, entities_db, forms_db,
    entities_db_service_manager,
) -> None:
    """The conflict check must also compare pins within one publish, not only
    against what is already persisted."""
    source_name = f"Client_{uuid.uuid4().hex[:8]}"
    target_name = f"Request_{uuid.uuid4().hex[:8]}"
    source_type = _entity_type(entities_db, source_name)
    target_type = _entity_type(entities_db, target_name)
    _active_form(forms_db, entities_db_service_manager, source_name, ["name"])
    relation_def_id = _declaration(
        entities_db, from_entity_type_id=source_type, to_entity_type_id=target_type
    )
    field_a, _ = _make_field(field_service)
    field_b, _ = _make_field(field_service)
    method_a, _ = _make_method(
        method_service, name="Mapper A", fields=[_input(field_a, inherit_from=f"{source_name}.name")]
    )
    method_b, _ = _make_method(
        method_service, name="Mapper B", fields=[_input(field_b, inherit_from=f"{source_name}.name")]
    )
    row_id = _draft(workflow_db, target_name)

    with pytest.raises(ValidationError, match="already maps it to"):
        _publish(
            manager,
            row_id,
            _definition(
                target_name,
                _states([MethodRef(method_id=method_a.method_id), MethodRef(method_id=method_b.method_id)]),
            ),
        )

    assert _relation_metadata(entities_db_service_manager, relation_def_id) == {}


# ── Nothing written when publish is blocked for any reason ───────────────────


def test_no_relation_metadata_write_when_publish_is_blocked(
    manager, workflow_db, method_service, field_service, entities_db, forms_db,
    entities_db_service_manager,
) -> None:
    source_name = f"Client_{uuid.uuid4().hex[:8]}"
    target_name = f"Request_{uuid.uuid4().hex[:8]}"
    source_type = _entity_type(entities_db, source_name)
    target_type = _entity_type(entities_db, target_name)
    _active_form(forms_db, entities_db_service_manager, source_name, ["name"])
    relation_def_id = _declaration(
        entities_db, from_entity_type_id=source_type, to_entity_type_id=target_type
    )
    good_field, _ = _make_field(field_service)
    bad_field, _ = _make_field(field_service)
    good_method, _ = _make_method(
        method_service, name="Good", fields=[_input(good_field, inherit_from=f"{source_name}.name")]
    )
    bad_method, _ = _make_method(
        method_service, name="Bad", fields=[_input(bad_field, inherit_from=f"{source_name}.nmae")],
    )
    row_id = _draft(workflow_db, target_name)

    with pytest.raises(ValidationError):
        _publish(
            manager,
            row_id,
            _definition(
                target_name,
                _states([MethodRef(method_id=good_method.method_id), MethodRef(method_id=bad_method.method_id)]),
            ),
        )

    # The good field's mapping must not have been written even though it was valid.
    assert _relation_metadata(entities_db_service_manager, relation_def_id) == {}


# ── A field with no inherit_from is unaffected ────────────────────────────────


def test_a_field_without_inherit_from_publishes_exactly_as_before(
    manager, workflow_db, method_service, field_service, entities_db
) -> None:
    target_name = f"Request_{uuid.uuid4().hex[:8]}"
    _entity_type(entities_db, target_name)
    field_id, field_key = _make_field(field_service)
    identity, _version = _make_method(
        method_service, name="Owned", fields=[_input(field_id)]
    )
    row_id = _draft(workflow_db, target_name)

    published = _publish(
        manager, row_id, _definition(target_name, _states([MethodRef(method_id=identity.method_id)]))
    )

    schema = published.state_machine.definition.entity_schema
    assert [field.field for field in schema.fields] == [field_key]
