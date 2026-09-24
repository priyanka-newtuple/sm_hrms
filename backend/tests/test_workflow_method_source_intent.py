"""Method-attach relation checks: source-intent fields, Entity Types -> Relations.

A Method field can declare a source intent (an entity type + field) without
knowing which workflow entity type will host it. Attaching such a method to a
state looks up a matching relation and writes an attributed entry into that
relation's `relation_metadata` — the same column and shape the legacy "Add
from related entity" flow uses, plus attribution so detach can clean up
exactly what it wrote and nothing else.
"""

from __future__ import annotations

import uuid

import pytest

from entities.db_models import EntitiesModelService
from entities.manager import EntitiesServiceManager
from entities.models.interface import RelationType
from entities.models.request import EntityRelationDeclarationCreateRequest, EntityTypeCreateRequest
from exceptions import ValidationError
from field_library.db_models import FieldLibraryModelService
from method_library.db_models import (
    MethodLibraryCategoryModel,
    MethodLibraryMethodModel,
    MethodLibraryMethodVersionFieldModel,
    MethodLibraryMethodVersionModel,
    MethodLibraryModelService,
    MethodLibraryOrgCounterModel,
)
from field_library.db_models import FieldLibraryFieldModel, FieldLibraryFieldVersionModel
from method_library.manager import MethodLibraryServiceManager
from method_library.models.request import MethodCreateRequest, MethodFieldInput
from workflow.db_models import WorkflowModelService
from workflow.manager import WorkflowServiceManager
from workflow.models.interface import (
    EntityField,
    EntitySchema,
    Guard,
    GuardType,
    MethodRef,
    State,
    StateMachineDefinition,
    Transition,
)
from workflow.models.request import StateMachineValidateRequest, WorkflowDraftUpdateRequest
from workflow_manager_factory import AllowAllEntityRolesManager, make_workflow_manager

ORG = "test-org-1"
_METHOD_ATTRIBUTION_KEY = "_method_attribution"


@pytest.fixture
def field_service(entities_db_service_manager) -> FieldLibraryModelService:
    return FieldLibraryModelService(entities_db_service_manager)


@pytest.fixture
def method_db_service(entities_db_service_manager) -> MethodLibraryModelService:
    return MethodLibraryModelService(entities_db_service_manager)


@pytest.fixture
def method_manager(method_db_service) -> MethodLibraryServiceManager:
    service = MethodLibraryServiceManager(method_db_service)
    service.start()
    return service


@pytest.fixture(autouse=True)
def clean_method_rows(method_db_service):
    """Purge this org's method/field rows, children before parents."""

    def _purge() -> None:
        with method_db_service._db_session() as session:
            for model in (
                MethodLibraryOrgCounterModel,
                MethodLibraryMethodVersionFieldModel,
                MethodLibraryMethodVersionModel,
                MethodLibraryMethodModel,
                MethodLibraryCategoryModel,
                FieldLibraryFieldVersionModel,
                FieldLibraryFieldModel,
            ):
                session.query(model).filter(model.organization_id == ORG).delete(
                    synchronize_session=False
                )
            session.commit()

    _purge()
    yield
    _purge()


@pytest.fixture
def workflow_manager(entities_db_service_manager, clean_entities_tables, method_db_service):
    """WorkflowServiceManager wired to the real entities + workflow + method-library DB."""
    from sqlalchemy import text

    from tests.conftest import ENTITIES_TEST_ORG_IDS

    engine = entities_db_service_manager.postgres_db_service().engine
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM workflow_state_machines WHERE organization_id = ANY(:ids)"),
            {"ids": list(ENTITIES_TEST_ORG_IDS)},
        )

    workflow_db = WorkflowModelService(database_service_manager=entities_db_service_manager)
    entities_db = EntitiesModelService(database_service_manager=entities_db_service_manager)
    entities = EntitiesServiceManager(
        entities_db,
        database_service_manager=entities_db_service_manager,
        config=None,
        roles_manager=AllowAllEntityRolesManager(),
    )
    entities.start()
    manager = make_workflow_manager(
        workflow_db,
        entities_db_service_manager,
        entities_service_manager=entities,
        method_library_db_model_service=method_db_service,
    )
    manager.start()
    yield manager


def _admin_actor(org_id: str = ORG) -> dict:
    return {"user_id": "admin-1", "organization_id": org_id, "roles": ["admin"]}


def _register_entity_type(workflow_manager: WorkflowServiceManager, *, name: str) -> str:
    response = workflow_manager.entities_service_manager.create_entity_type_for_actor(
        _admin_actor(),
        EntityTypeCreateRequest(name=name, description=f"test type {name}"),
    )
    return response.entity_type_id


def _declare_relation(
    workflow_manager: WorkflowServiceManager,
    *,
    from_type_id: str,
    to_type_id: str,
    relation_metadata: dict | None = None,
) -> str:
    record = workflow_manager.entities_service_manager.db_model_service.create_entity_relation_declaration(
        EntityRelationDeclarationCreateRequest(
            organization_id=ORG,
            from_entity_type_id=from_type_id,
            to_entity_type_id=to_type_id,
            relation_type=RelationType.SNAPSHOT,
            relation_metadata=relation_metadata or {},
        ),
        default_relation_type=RelationType.SNAPSHOT.value,
    )
    return record.relation_def_id


def _relation_metadata(workflow_manager, *, from_type_id: str, to_type_id: str) -> dict:
    relation = workflow_manager.entities_service_manager.db_model_service.get_active_relation_declaration_for_pair(
        organization_id=ORG, from_entity_type_id=from_type_id, to_entity_type_id=to_type_id
    )
    assert relation is not None
    return dict(relation.relation_metadata or {})


def _make_method_with_source_intent(
    method_manager: MethodLibraryServiceManager,
    field_service: FieldLibraryModelService,
    *,
    name: str,
    source_entity_type: str,
    source_field_key: str,
    field_key_suffix: str | None = None,
) -> tuple[str, str]:
    """Create a method with one field carrying a source intent.

    Returns (method_id, the field's own field_key on the workflow's schema).
    """
    suffix = field_key_suffix or uuid.uuid4().hex[:8]
    created_field = field_service.create_field(
        organization_id=ORG,
        name=f"Field {suffix}",
        field_key=f"field_{suffix}",
        field_type="text",
        description=None,
        settings={},
        created_by="user-a",
    )
    created_method = method_manager.create_method_for_actor(
        _admin_actor(),
        MethodCreateRequest(
            name=name,
            fields=[
                MethodFieldInput(
                    library_field_id=created_field.identity.library_field_id,
                    label=name,
                    position=0,
                    source_entity_type=source_entity_type,
                    source_field_key=source_field_key,
                )
            ],
        ),
    )
    return created_method.identity.method_id, created_field.identity.field_key


def _draft_definition(entity_type: str, state_name: str, method_refs: list[MethodRef]) -> StateMachineDefinition:
    return StateMachineDefinition(
        machine_key=f"wf_{state_name}_{uuid.uuid4().hex[:6]}",
        name="Source Intent Test Workflow",
        description="",
        entity_type=entity_type,
        entity_schema=EntitySchema(entity_type=entity_type, fields=[]),
        states=[State(name=state_name, tags=["initial"], order=1, method_refs=method_refs)],
        initial_state=state_name,
        transitions=[],
    )


def _seed_draft(workflow_manager, definition: StateMachineDefinition) -> str:
    created = workflow_manager.workflow_db.create_state_machine_draft(
        organization_id=ORG,
        machine_key=definition.machine_key,
        machine_name=definition.machine_key,
        definition=definition.model_dump(mode="json"),
    )
    assert created.id is not None
    return created.id


def _save(workflow_manager, row_id: str, definition: StateMachineDefinition):
    return workflow_manager.update_workflow_draft_for_actor(
        _admin_actor(),
        row_id,
        WorkflowDraftUpdateRequest(definition=definition.model_dump(mode="json")),
    )


def test_attach_with_matching_relation_writes_an_attributed_entry(
    workflow_manager, method_manager, field_service
) -> None:
    to_type_id = _register_entity_type(workflow_manager, name="SI_Application")
    from_type_id = _register_entity_type(workflow_manager, name="SI_Candidate")
    _declare_relation(workflow_manager, from_type_id=from_type_id, to_type_id=to_type_id)

    method_id, field_key = _make_method_with_source_intent(
        method_manager,
        field_service,
        name="Candidate Email",
        source_entity_type="SI_Candidate",
        source_field_key="email",
    )

    empty = _draft_definition("SI_Application", "start", [])
    row_id = _seed_draft(workflow_manager, empty)

    attached = _draft_definition("SI_Application", "start", [MethodRef(method_id=method_id)])
    _save(workflow_manager, row_id, attached)

    metadata = _relation_metadata(workflow_manager, from_type_id=from_type_id, to_type_id=to_type_id)
    assert metadata["SI_Candidate.email"] == f"SI_Application.{field_key}"
    attribution = metadata[_METHOD_ATTRIBUTION_KEY]
    assert attribution == [
        {
            "method_id": method_id,
            "field_key": field_key,
            "source_key": "SI_Candidate.email",
            "target_key": f"SI_Application.{field_key}",
        }
    ]


def test_attach_without_a_matching_relation_is_blocked_and_writes_nothing(
    workflow_manager, method_manager, field_service
) -> None:
    to_type_id = _register_entity_type(workflow_manager, name="SI_Application2")
    _register_entity_type(workflow_manager, name="SI_Candidate2")  # no relation declared

    method_id, _field_key = _make_method_with_source_intent(
        method_manager,
        field_service,
        name="Candidate Email 2",
        source_entity_type="SI_Candidate2",
        source_field_key="email",
    )

    empty = _draft_definition("SI_Application2", "start", [])
    row_id = _seed_draft(workflow_manager, empty)

    attached = _draft_definition("SI_Application2", "start", [MethodRef(method_id=method_id)])
    with pytest.raises(ValidationError, match="no relation exists"):
        _save(workflow_manager, row_id, attached)

    # No partial write: the persisted draft still has no method_refs.
    persisted = workflow_manager.workflow_db.get_state_machine_by_row_id(
        organization_id=ORG, row_id=row_id
    )
    assert persisted.definition["states"][0]["method_refs"] == []


def test_detach_removes_only_its_own_attributed_entries(
    workflow_manager, method_manager, field_service
) -> None:
    to_type_id = _register_entity_type(workflow_manager, name="SI_Application3")
    from_type_id = _register_entity_type(workflow_manager, name="SI_Candidate3")
    _declare_relation(
        workflow_manager,
        from_type_id=from_type_id,
        to_type_id=to_type_id,
        relation_metadata={"SI_Candidate3.legacy_field": "SI_Application3.legacy_target"},
    )

    method_a, field_a = _make_method_with_source_intent(
        method_manager,
        field_service,
        name="Method A",
        source_entity_type="SI_Candidate3",
        source_field_key="email",
    )
    method_b, field_b = _make_method_with_source_intent(
        method_manager,
        field_service,
        name="Method B",
        source_entity_type="SI_Candidate3",
        source_field_key="phone",
    )

    empty = _draft_definition("SI_Application3", "start", [])
    row_id = _seed_draft(workflow_manager, empty)
    both_attached = _draft_definition(
        "SI_Application3", "start", [MethodRef(method_id=method_a), MethodRef(method_id=method_b)]
    )
    _save(workflow_manager, row_id, both_attached)

    metadata = _relation_metadata(workflow_manager, from_type_id=from_type_id, to_type_id=to_type_id)
    assert "SI_Candidate3.legacy_field" in metadata
    assert "SI_Candidate3.email" in metadata
    assert "SI_Candidate3.phone" in metadata
    assert {a["method_id"] for a in metadata[_METHOD_ATTRIBUTION_KEY]} == {method_a, method_b}

    # Detach method A only.
    only_b = _draft_definition("SI_Application3", "start", [MethodRef(method_id=method_b)])
    _save(workflow_manager, row_id, only_b)

    metadata = _relation_metadata(workflow_manager, from_type_id=from_type_id, to_type_id=to_type_id)
    # Method A's own entry is gone.
    assert "SI_Candidate3.email" not in metadata
    # The legacy manual entry (no attribution) is untouched.
    assert metadata["SI_Candidate3.legacy_field"] == "SI_Application3.legacy_target"
    # Method B's entry and attribution are untouched.
    assert metadata["SI_Candidate3.phone"] == f"SI_Application3.{field_b}"
    remaining_attribution = metadata[_METHOD_ATTRIBUTION_KEY]
    assert len(remaining_attribution) == 1
    assert remaining_attribution[0]["method_id"] == method_b
    assert remaining_attribution[0]["field_key"] == field_b


def test_reattach_after_detach_writes_a_fresh_entry(
    workflow_manager, method_manager, field_service
) -> None:
    to_type_id = _register_entity_type(workflow_manager, name="SI_Application4")
    from_type_id = _register_entity_type(workflow_manager, name="SI_Candidate4")
    _declare_relation(workflow_manager, from_type_id=from_type_id, to_type_id=to_type_id)

    method_id, field_key = _make_method_with_source_intent(
        method_manager,
        field_service,
        name="Candidate Email 4",
        source_entity_type="SI_Candidate4",
        source_field_key="email",
    )

    empty = _draft_definition("SI_Application4", "start", [])
    row_id = _seed_draft(workflow_manager, empty)

    attached = _draft_definition("SI_Application4", "start", [MethodRef(method_id=method_id)])
    _save(workflow_manager, row_id, attached)
    _save(workflow_manager, row_id, empty)  # detach

    metadata = _relation_metadata(workflow_manager, from_type_id=from_type_id, to_type_id=to_type_id)
    assert "SI_Candidate4.email" not in metadata
    assert metadata.get(_METHOD_ATTRIBUTION_KEY, []) == []

    _save(workflow_manager, row_id, attached)  # re-attach

    metadata = _relation_metadata(workflow_manager, from_type_id=from_type_id, to_type_id=to_type_id)
    assert metadata["SI_Candidate4.email"] == f"SI_Application4.{field_key}"
    attribution = metadata[_METHOD_ATTRIBUTION_KEY]
    assert len(attribution) == 1
    assert attribution[0]["method_id"] == method_id
    assert attribution[0]["field_key"] == field_key


def test_reattaching_the_same_method_twice_does_not_duplicate_the_entry(
    workflow_manager, method_manager, field_service
) -> None:
    """Detach then re-attach in one save (net: still attached, but the ref
    momentarily left and re-entered the diff) must not double the entry."""
    to_type_id = _register_entity_type(workflow_manager, name="SI_Application5")
    from_type_id = _register_entity_type(workflow_manager, name="SI_Candidate5")
    _declare_relation(workflow_manager, from_type_id=from_type_id, to_type_id=to_type_id)

    method_id, field_key = _make_method_with_source_intent(
        method_manager,
        field_service,
        name="Candidate Email 5",
        source_entity_type="SI_Candidate5",
        source_field_key="email",
    )

    empty = _draft_definition("SI_Application5", "start", [])
    row_id = _seed_draft(workflow_manager, empty)
    attached = _draft_definition("SI_Application5", "start", [MethodRef(method_id=method_id)])

    _save(workflow_manager, row_id, attached)
    _save(workflow_manager, row_id, empty)
    _save(workflow_manager, row_id, attached)
    # Re-saving the same attached state again — no diff, must stay a no-op.
    _save(workflow_manager, row_id, attached)

    metadata = _relation_metadata(workflow_manager, from_type_id=from_type_id, to_type_id=to_type_id)
    assert metadata["SI_Candidate5.email"] == f"SI_Application5.{field_key}"
    assert len(metadata[_METHOD_ATTRIBUTION_KEY]) == 1


# ── Guard fields contributed by an attached Method ───────────────────────────


def _make_plain_method(
    method_manager: MethodLibraryServiceManager,
    field_service: FieldLibraryModelService,
    *,
    name: str,
) -> tuple[str, str]:
    """Create a method with one ordinary field — no source intent.

    Returns (method_id, the field_key that method contributes).
    """
    suffix = uuid.uuid4().hex[:8]
    created_field = field_service.create_field(
        organization_id=ORG,
        name=f"Guard field {suffix}",
        field_key=f"guard_field_{suffix}",
        field_type="text",
        description=None,
        settings={},
        created_by="user-a",
    )
    created_method = method_manager.create_method_for_actor(
        _admin_actor(),
        MethodCreateRequest(
            name=name,
            fields=[
                MethodFieldInput(
                    library_field_id=created_field.identity.library_field_id,
                    label=name,
                    position=0,
                )
            ],
        ),
    )
    return created_method.identity.method_id, created_field.identity.field_key


def _guarded_definition(
    entity_type: str,
    *,
    guard_field: str,
    method_refs: list[MethodRef],
) -> StateMachineDefinition:
    """Two states, one transition, one field_present guard on `guard_field`.

    `method_refs` are pinned to INITIAL, the state the transition leaves, so
    the guard is scoped against exactly those methods.
    """
    return StateMachineDefinition(
        machine_key=f"wf_guard_{uuid.uuid4().hex[:6]}",
        name="Guard field test workflow",
        description="",
        entity_type=entity_type,
        entity_schema=EntitySchema(
            entity_type=entity_type,
            fields=[
                EntityField(
                    field="request_name",
                    type="string",
                    required=False,
                    nullable=True,
                    default="",
                    description="Request name",
                )
            ],
        ),
        states=[
            State(name="INITIAL", tags=["initial"], order=1, method_refs=method_refs),
            State(name="TERMINATION", tags=["terminal"], order=2),
        ],
        initial_state="INITIAL",
        transitions=[
            Transition(
                key="initial__to__termination",
                trigger="to_termination",
                label="To termination",
                from_state="INITIAL",
                to_state="TERMINATION",
                required_fields=[],
                guards=[
                    Guard(
                        type=GuardType.FIELD_PRESENT,
                        field=guard_field,
                        value="",
                        message="Field is required",
                    )
                ],
                pre_transition_tasks=[],
                post_transition_tasks=[],
                auto_transition=None,
                description="",
            )
        ],
    )


def _validate(workflow_manager, definition: StateMachineDefinition):
    return workflow_manager.validate_candidate_workflow_for_actor(
        _admin_actor(),
        StateMachineValidateRequest(
            machine_name=definition.machine_key, definition=definition
        ),
    )


def _errors(report) -> list[str]:
    return [issue.message for issue in report.issues if issue.severity == "error"]


def test_guard_may_reference_a_field_the_states_method_contributes(
    workflow_manager, method_manager, field_service
) -> None:
    """The live repro: a guard on a field only an attached Method defines."""
    entity_type = "GF_Request"
    _register_entity_type(workflow_manager, name=entity_type)
    method_id, method_field = _make_plain_method(
        method_manager, field_service, name="Hello Test Method"
    )

    definition = _guarded_definition(
        entity_type,
        guard_field=method_field,
        method_refs=[MethodRef(method_id=method_id)],
    )
    response = _validate(workflow_manager, definition)

    assert _errors(response.validation_report) == []
    assert response.validation_report.valid is True


def test_guard_on_a_field_no_schema_or_method_provides_is_still_rejected(
    workflow_manager, method_manager, field_service
) -> None:
    """The check must not have been removed — a truly unknown field still fails."""
    entity_type = "GF_Request_Bad"
    _register_entity_type(workflow_manager, name=entity_type)
    method_id, _method_field = _make_plain_method(
        method_manager, field_service, name="Unrelated Method"
    )

    definition = _guarded_definition(
        entity_type,
        guard_field="totally_bogus_field_xyz",
        method_refs=[MethodRef(method_id=method_id)],
    )
    response = _validate(workflow_manager, definition)

    errors = _errors(response.validation_report)
    assert any("totally_bogus_field_xyz" in message for message in errors), errors
    assert response.validation_report.valid is not True


def test_guard_on_a_plain_entity_schema_field_still_passes(workflow_manager) -> None:
    """The original entity-schema-only path is untouched."""
    entity_type = "GF_Request_Plain"
    _register_entity_type(workflow_manager, name=entity_type)

    definition = _guarded_definition(
        entity_type, guard_field="request_name", method_refs=[]
    )
    response = _validate(workflow_manager, definition)

    assert _errors(response.validation_report) == []
    assert response.validation_report.valid is True
