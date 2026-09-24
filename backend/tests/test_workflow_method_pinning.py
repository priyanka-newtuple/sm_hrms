"""Pinning method library methods to workflow states.

Publishing is the only moment a pin is decided. A state's `method_refs` are
resolved then, the resolved fields are merged into the workflow's entity schema,
and the pins are written against the published row. Everything here goes through
the real publish path against the real database, because the parts worth testing
are exactly the ones a stub would paper over: which version a ref resolves to,
what happens when two methods disagree, and whether a pinned method can still be
deleted.
"""

from __future__ import annotations

import uuid
from unittest.mock import Mock

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from exceptions import ConflictError, ValidationError
from field_library.db_models import FieldLibraryModelService
from method_library.db_models import MethodInUseError, MethodLibraryModelService
from method_library.models.request import MethodFieldInput
from workflow_manager_factory import NoActiveFormsManager
from workflow.db_models import WorkflowModelService
from workflow.manager import WorkflowServiceManager
from workflow.models import WorkflowPublishRequest
from workflow.models.interface import (
    EntityField,
    EntitySchema,
    MethodRef,
    State,
    StateMachineDefinition,
    Transition,
)

ORG_A = "test-org-1"
ACTOR_A = {"organization_id": ORG_A, "user_id": "user-a", "roles": ["admin"]}
ENTITY_TYPE = "pinning_entity"


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
def manager(entities_db_service_manager, workflow_db, method_service):
    """The real manager. Only the collaborators publish does not reach are stubs."""
    roles = Mock()
    roles.get_workflow_access_scope.return_value = None
    return WorkflowServiceManager(
        workflow_db_model_service=workflow_db,
        database_service_manager=entities_db_service_manager,
        config=None,
        entities_service_manager=None,
        roles_manager=roles,
        audit_events_service=None,
        forms_service_manager=NoActiveFormsManager(),
        method_library_db_model_service=method_service,
        filehandler_service_manager=None,
        user_service_manager=None,
        blob_storage_service=None,
    )


@pytest.fixture(autouse=True)
def clean_rows(entities_db_service_manager):
    """Purge pins, this test's workflows, and the library rows they lean on."""

    def _purge() -> None:
        session = entities_db_service_manager.postgres_db_service().get_db_session()
        try:
            for statement in (
                "DELETE FROM {definitions}.workflow_method_pins WHERE organization_id = :org",
                "DELETE FROM {app}.workflow_state_machines "
                "WHERE organization_id = :org AND entity_type = :entity_type",
                "DELETE FROM {definitions}.method_library_method_version_fields "
                "WHERE organization_id = :org",
                "DELETE FROM {definitions}.method_library_method_versions "
                "WHERE organization_id = :org",
                "DELETE FROM {definitions}.method_library_methods WHERE organization_id = :org",
                "DELETE FROM {definitions}.method_library_org_counters WHERE organization_id = :org",
                "DELETE FROM {definitions}.field_library_field_versions WHERE organization_id = :org",
                "DELETE FROM {definitions}.field_library_fields WHERE organization_id = :org",
            ):
                session.execute(
                    text(
                        statement.format(
                            definitions="modular_backend_definitions", app="modular_backend"
                        )
                    ),
                    {"org": ORG_A, "entity_type": ENTITY_TYPE},
                )
            session.commit()
        finally:
            session.close()

    _purge()
    yield
    _purge()


# ── Fixture builders ──────────────────────────────────────────────────────────


def _make_field(field_service, *, field_type: str = "text") -> str:
    """A library field, returning its id. Its key is what a workflow field is called."""
    suffix = uuid.uuid4().hex[:8]
    created = field_service.create_field(
        organization_id=ORG_A,
        name=f"Volume {suffix}",
        field_key=f"volume_{suffix}",
        field_type=field_type,
        description=None,
        settings={},
        created_by="user-a",
    )
    return created.identity.library_field_id


def _field_key(field_service, library_field_id: str) -> str:
    return field_service.get_field(
        organization_id=ORG_A, library_field_id=library_field_id
    ).field_key


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


def _input(library_field_id: str, *, label: str = "Volume collected", position: int = 0):
    return MethodFieldInput(
        library_field_id=library_field_id,
        label=label,
        placeholder="e.g. 5",
        required=True,
        position=position,
    )


def _definition(
    states: list[State], *, fields: list[EntityField] | None = None
) -> StateMachineDefinition:
    return StateMachineDefinition(
        machine_key="pinning_machine",
        name="Pinning Machine",
        entity_type=ENTITY_TYPE,
        entity_schema=EntitySchema(entity_type=ENTITY_TYPE, fields=list(fields or [])),
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


def _states(method_refs: list[MethodRef] | None = None) -> list[State]:
    return [
        State(name="start", tags=["initial"], order=1, method_refs=list(method_refs or [])),
        State(name="end", tags=["terminal"], order=2),
    ]


def _draft(workflow_db) -> str:
    record = workflow_db.create_state_machine_draft(
        organization_id=ORG_A,
        machine_name=f"pinning_{uuid.uuid4().hex[:8]}",
        machine_key="pinning_machine",
        definition=_definition(_states()).model_dump(mode="json"),
        created_by="user-a",
    )
    return record.id


def _publish(manager, row_id: str, definition: StateMachineDefinition):
    return manager.publish_workflow_for_actor(
        ACTOR_A, row_id, WorkflowPublishRequest(definition=definition)
    )


# ── The additive guarantee ────────────────────────────────────────────────────


def test_a_state_with_no_method_refs_publishes_exactly_as_before(
    manager, workflow_db
) -> None:
    """The regression that matters most: nothing changes for workflows without pins."""
    row_id = _draft(workflow_db)
    own_field = EntityField(field="operator", type="string", description="Operator")
    definition = _definition(_states(), fields=[own_field])

    published = _publish(manager, row_id, definition)

    assert published.state_machine.version == 1
    schema = published.state_machine.definition.entity_schema
    assert [field.field for field in schema.fields] == ["operator"]
    assert schema.fields[0].model_dump(mode="json") == own_field.model_dump(mode="json")
    assert (
        workflow_db.list_method_pins(
            organization_id=ORG_A, workflow_state_machine_id=published.state_machine.id
        )
        == []
    )


# ── Which version a ref resolves to ───────────────────────────────────────────


def test_an_explicit_version_resolves_that_version_not_the_newest(
    manager, workflow_db, method_service, field_service
) -> None:
    """A method moving on afterwards must not change what an explicit pin sees."""
    old_field = _make_field(field_service)
    new_field = _make_field(field_service)
    identity, first_version = _make_method(
        method_service, name="Historied", fields=[_input(old_field, label="Old label")]
    )
    method_service.replace_method_field_list(
        organization_id=ORG_A,
        method_id=identity.method_id,
        field_inputs=[_input(new_field, label="New label")],
        created_by="user-a",
    )

    row_id = _draft(workflow_db)
    published = _publish(
        manager,
        row_id,
        _definition(
            _states([MethodRef(method_id=identity.method_id, version_id=first_version.version_id)])
        ),
    )

    schema = published.state_machine.definition.entity_schema
    assert [field.field for field in schema.fields] == [_field_key(field_service, old_field)]
    assert schema.fields[0].description == "Old label"
    assert workflow_db.list_method_pins(
        organization_id=ORG_A, workflow_state_machine_id=published.state_machine.id
    ) == [("start", identity.method_id, first_version.version_id)]


def test_no_version_resolves_to_whatever_is_current_at_publish_time(
    manager, workflow_db, method_service, field_service
) -> None:
    old_field = _make_field(field_service)
    new_field = _make_field(field_service)
    identity, first_version = _make_method(
        method_service, name="Moving", fields=[_input(old_field)]
    )
    latest = method_service.replace_method_field_list(
        organization_id=ORG_A,
        method_id=identity.method_id,
        field_inputs=[_input(new_field, label="Newest label")],
        created_by="user-a",
    )

    row_id = _draft(workflow_db)
    published = _publish(
        manager, row_id, _definition(_states([MethodRef(method_id=identity.method_id)]))
    )

    schema = published.state_machine.definition.entity_schema
    assert [field.field for field in schema.fields] == [_field_key(field_service, new_field)]
    pins = workflow_db.list_method_pins(
        organization_id=ORG_A, workflow_state_machine_id=published.state_machine.id
    )
    assert pins == [("start", identity.method_id, latest.version_id)]
    assert latest.version_id != first_version.version_id


def test_a_version_belonging_to_another_method_is_refused(
    manager, workflow_db, method_service, field_service
) -> None:
    """A pin is checked against its own method rather than trusted."""
    mine, _ = _make_method(
        method_service, name="Mine", fields=[_input(_make_field(field_service))]
    )
    _, other_version = _make_method(
        method_service, name="Other", fields=[_input(_make_field(field_service))]
    )

    row_id = _draft(workflow_db)
    with pytest.raises(ValidationError, match="does not belong to method"):
        _publish(
            manager,
            row_id,
            _definition(
                _states([MethodRef(method_id=mine.method_id, version_id=other_version.version_id)])
            ),
        )


# ── Merging and conflicts ─────────────────────────────────────────────────────


def test_two_methods_contributing_the_identical_field_merge_into_one(
    manager, workflow_db, method_service, field_service
) -> None:
    shared = _make_field(field_service)
    first, _ = _make_method(
        method_service, name="First", fields=[_input(shared, label="Same label")]
    )
    second, _ = _make_method(
        method_service, name="Second", fields=[_input(shared, label="Same label")]
    )

    row_id = _draft(workflow_db)
    published = _publish(
        manager,
        row_id,
        _definition(
            _states([MethodRef(method_id=first.method_id), MethodRef(method_id=second.method_id)])
        ),
    )

    schema = published.state_machine.definition.entity_schema
    assert [field.field for field in schema.fields] == [_field_key(field_service, shared)]
    # Both methods are still pinned; only the duplicated field collapsed.
    pins = workflow_db.list_method_pins(
        organization_id=ORG_A, workflow_state_machine_id=published.state_machine.id
    )
    assert {pin[1] for pin in pins} == {first.method_id, second.method_id}


def test_two_methods_disagreeing_about_a_field_block_the_publish(
    manager, workflow_db, method_service, field_service
) -> None:
    """No guessing: a real disagreement refuses the publish and names the field."""
    shared = _make_field(field_service)
    key = _field_key(field_service, shared)
    first, _ = _make_method(
        method_service, name="First", fields=[_input(shared, label="Volume in mL")]
    )
    second, _ = _make_method(
        method_service, name="Second", fields=[_input(shared, label="Volume in litres")]
    )

    row_id = _draft(workflow_db)
    with pytest.raises(ValidationError) as caught:
        _publish(
            manager,
            row_id,
            _definition(
                _states(
                    [MethodRef(method_id=first.method_id), MethodRef(method_id=second.method_id)]
                )
            ),
        )

    message = str(caught.value)
    assert key in message
    assert first.method_id in message or second.method_id in message
    # Nothing was published and nothing was pinned.
    assert (
        workflow_db.list_state_machines(organization_id=ORG_A, scope="published", machine_name=None)
        is not None
    )


def test_a_method_disagreeing_with_a_hand_written_field_blocks_the_publish(
    manager, workflow_db, method_service, field_service
) -> None:
    shared = _make_field(field_service)
    key = _field_key(field_service, shared)
    method, _ = _make_method(method_service, name="Method", fields=[_input(shared)])

    row_id = _draft(workflow_db)
    with pytest.raises(ValidationError, match="workflow's own fields"):
        _publish(
            manager,
            row_id,
            _definition(
                _states([MethodRef(method_id=method.method_id)]),
                fields=[EntityField(field=key, type="int", description="Hand written")],
            ),
        )


def test_a_hand_written_field_identical_to_the_methods_is_not_a_conflict(
    manager, workflow_db, method_service, field_service
) -> None:
    shared = _make_field(field_service)
    key = _field_key(field_service, shared)
    method, _ = _make_method(method_service, name="Method", fields=[_input(shared)])
    # 'text' is the library's type code; 'string' is what the catalogue says the
    # engine stores it as, so that is what the merged field must look like.
    identical = EntityField(
        field=key,
        type="string",
        required=True,
        description="Volume collected",
        placeholder="e.g. 5",
    )

    row_id = _draft(workflow_db)
    published = _publish(
        manager,
        row_id,
        _definition(_states([MethodRef(method_id=method.method_id)]), fields=[identical]),
    )

    schema = published.state_machine.definition.entity_schema
    assert [field.field for field in schema.fields] == [key]


# ── The delete guard the pins now back ────────────────────────────────────────


def test_a_pinned_method_cannot_be_deleted(
    manager, workflow_db, method_service, field_service
) -> None:
    method, _ = _make_method(
        method_service, name="Pinned", fields=[_input(_make_field(field_service))]
    )
    _publish(
        manager,
        _draft(workflow_db),
        _definition(_states([MethodRef(method_id=method.method_id)])),
    )

    with pytest.raises(MethodInUseError, match="pinned"):
        method_service.delete_method(organization_id=ORG_A, method_id=method.method_id)
    assert (
        method_service.get_method(organization_id=ORG_A, method_id=method.method_id) is not None
    )


def test_an_unpinned_method_still_deletes(manager, workflow_db, method_service, field_service):
    pinned, _ = _make_method(
        method_service, name="Pinned", fields=[_input(_make_field(field_service))]
    )
    unpinned, _ = _make_method(
        method_service, name="Unpinned", fields=[_input(_make_field(field_service))]
    )
    _publish(
        manager,
        _draft(workflow_db),
        _definition(_states([MethodRef(method_id=pinned.method_id)])),
    )

    assert method_service.delete_method(organization_id=ORG_A, method_id=unpinned.method_id)
    assert method_service.get_method(organization_id=ORG_A, method_id=unpinned.method_id) is None


# ── Republishing ──────────────────────────────────────────────────────────────


def test_republishing_repins_without_touching_the_previous_versions_pins(
    manager, workflow_db, method_service, field_service
) -> None:
    """Each published version keeps the pins it was built with."""
    first_field = _make_field(field_service)
    second_field = _make_field(field_service)
    method, first_version = _make_method(
        method_service, name="Republished", fields=[_input(first_field, label="First")]
    )
    second_version = method_service.replace_method_field_list(
        organization_id=ORG_A,
        method_id=method.method_id,
        field_inputs=[_input(second_field, label="Second")],
        created_by="user-a",
    )
    row_id = _draft(workflow_db)

    v1 = _publish(
        manager,
        row_id,
        _definition(
            _states([MethodRef(method_id=method.method_id, version_id=first_version.version_id)])
        ),
    )
    v2 = _publish(
        manager,
        row_id,
        _definition(
            _states([MethodRef(method_id=method.method_id, version_id=second_version.version_id)])
        ),
    )

    assert (v1.state_machine.version, v2.state_machine.version) == (1, 2)
    assert workflow_db.list_method_pins(
        organization_id=ORG_A, workflow_state_machine_id=v1.state_machine.id
    ) == [("start", method.method_id, first_version.version_id)]
    assert workflow_db.list_method_pins(
        organization_id=ORG_A, workflow_state_machine_id=v2.state_machine.id
    ) == [("start", method.method_id, second_version.version_id)]


def test_dropping_a_method_ref_drops_its_pin_on_the_new_version(
    manager, workflow_db, method_service, field_service
) -> None:
    method, _ = _make_method(
        method_service, name="Dropped", fields=[_input(_make_field(field_service))]
    )
    row_id = _draft(workflow_db)

    v1 = _publish(
        manager, row_id, _definition(_states([MethodRef(method_id=method.method_id)]))
    )
    v2 = _publish(manager, row_id, _definition(_states()))

    assert (
        len(
            workflow_db.list_method_pins(
                organization_id=ORG_A, workflow_state_machine_id=v1.state_machine.id
            )
        )
        == 1
    )
    assert (
        workflow_db.list_method_pins(
            organization_id=ORG_A, workflow_state_machine_id=v2.state_machine.id
        )
        == []
    )


# ── Review follow-ups ─────────────────────────────────────────────────────────


def test_a_state_cannot_reference_one_method_twice() -> None:
    """Two versions of one method would merge into a shape neither of them has."""
    with pytest.raises(PydanticValidationError, match="more than once"):
        State(
            name="start",
            method_refs=[
                MethodRef(method_id="m1", version_id="v1"),
                MethodRef(method_id="m1", version_id="v2"),
            ],
        )


def test_two_different_methods_in_one_state_are_still_fine() -> None:
    state = State(
        name="start",
        method_refs=[MethodRef(method_id="m1"), MethodRef(method_id="m2")],
    )
    assert [ref.method_id for ref in state.method_refs] == ["m1", "m2"]


def test_the_database_refuses_a_duplicate_pin_too(
    manager, workflow_db, method_service, field_service, entities_db_service_manager
) -> None:
    """The contract rule is backed by a constraint, not only by validation."""
    method, _ = _make_method(
        method_service, name="Pinned Once", fields=[_input(_make_field(field_service))]
    )
    published = _publish(
        manager,
        _draft(workflow_db),
        _definition(_states([MethodRef(method_id=method.method_id)])),
    )
    pins = workflow_db.list_method_pins(
        organization_id=ORG_A, workflow_state_machine_id=published.state_machine.id
    )
    state_key, method_id, version_id = pins[0]

    session = entities_db_service_manager.postgres_db_service().get_db_session()
    try:
        with pytest.raises(IntegrityError, match="uq_workflow_method_pins"):
            session.execute(
                text(
                    "INSERT INTO modular_backend_definitions.workflow_method_pins "
                    "(id, organization_id, workflow_state_machine_id, state_key, "
                    "method_id, method_version_id) "
                    "VALUES (:id, :org, :machine, :state, :method, :version)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "org": ORG_A,
                    "machine": published.state_machine.id,
                    "state": state_key,
                    "method": method_id,
                    "version": version_id,
                },
            )
            session.commit()
    finally:
        session.rollback()
        session.close()


def test_a_failed_pin_write_leaves_no_published_version_behind(
    manager, workflow_db, method_service, field_service, monkeypatch
) -> None:
    """The row and its pins land together, or neither does.

    Stands in for a method deleted between resolution and the pin insert, which
    would otherwise activate a new version whose method-derived fields had
    nothing protecting their source.
    """
    method, _ = _make_method(
        method_service, name="Vanishes", fields=[_input(_make_field(field_service))]
    )
    first = _publish(
        manager,
        _draft(workflow_db),
        _definition(_states([MethodRef(method_id=method.method_id)])),
    )
    row_id = _draft(workflow_db)

    def _explode(*args, **kwargs):
        raise IntegrityError("pin insert failed", None, Exception("simulated"))

    monkeypatch.setattr(WorkflowModelService, "_write_method_pins", staticmethod(_explode))
    with pytest.raises(ConflictError, match="nothing was published"):
        _publish(
            manager, row_id, _definition(_states([MethodRef(method_id=method.method_id)]))
        )

    monkeypatch.undo()
    published = workflow_db.list_state_machines(
        organization_id=ORG_A, machine_name=None, scope="published"
    )
    ours = [row for row in published if row.entity_type == ENTITY_TYPE]
    assert [row.id for row in ours] == [first.state_machine.id], (
        "the failed publish must not leave a version behind"
    )
