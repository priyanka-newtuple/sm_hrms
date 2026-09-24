"""Method-block-level field inheritance (`ownership='inherited'`).

The additive counterpart to `inherit_from`. Where `inherit_from` is projected
into `entity_type_relations.relation_metadata` at publish - and so applies to
every record of the entity type - `ownership='inherited'` is recorded only on
the published workflow's `entity_schema` and resolved per record from the
workflow it is enrolled in. Nothing is written to the relation.

Covered here:
  - the migration is idempotent and cleanly reversible (run against the same
    dev Postgres the app uses, restored in a `finally`);
  - the request model refuses the combinations that can never resolve;
  - publish blocks a pin whose source type has no declared relation, exactly
    like the inherit_from guard, and does NOT write relation_metadata on
    success;
  - the value resolves for a record enrolled in a workflow whose pinned block
    opted in, and does NOT resolve for a record of the same type that is not,
    which is the per-block scoping this exists for;
  - the blanket relation_metadata path (the pre-existing mechanism) resolves
    byte-for-byte as before, with no enrollment involved at all;
  - the RBAC helper reports the per-block field as overlay-resolved.

Regression baseline: the brief suggested CRM's account->opportunity `region`
mapping. That data comes from an uncommitted backfill not present on every
checkout, so the baseline here is self-contained instead: a declaration with
an explicit relation_metadata mapping, built by the test.
"""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import text

from entities.db_models import (
    EntitiesModelService,
    EntityRecordModel,
    EntityRelationModel,
    EntityStateRuntimeModel,
)
from entities.manager import EntitiesServiceManager
from entities.models.interface import RelationType
from entities.models.request import (
    EntityRecordCreateRequest,
    EntityRelationDeclarationCreateRequest,
    EntityTypeCreateRequest,
    EntityRecordUpdateRequest,
)
from exceptions import AuthorizationError, ValidationError
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
    FieldOwnership,
    MethodRef,
    State,
    StateMachineDefinition,
    Transition,
)

ORG_A = "test-org-1"
ACTOR_A = {"organization_id": ORG_A, "user_id": "user-a", "roles": ["admin"]}
DEFINITIONS = "modular_backend_definitions"
APP = "modular_backend"

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "2026_09_06_0001_add_ownership_to_method_fields.py"
)


# ── Fixtures (same shape as test_workflow_inherited_method_fields.py) ─────────


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


def _qualified(model) -> str:
    schema = model.__table__.schema
    return f"{schema}.{model.__tablename__}" if schema else model.__tablename__


@pytest.fixture(autouse=True)
def clean_rows(entities_db_service_manager):
    """Purge every row this file creates, children before parents. Runtime
    tables (records, links, enrollments) are named off the models so this
    follows them if their schema ever moves."""

    def _purge() -> None:
        session = entities_db_service_manager.postgres_db_service().get_db_session()
        try:
            for statement in (
                f"DELETE FROM {_qualified(EntityStateRuntimeModel)} WHERE organization_id = :org",
                f"DELETE FROM {_qualified(EntityRelationModel)} WHERE organization_id = :org",
                f"DELETE FROM {_qualified(EntityRecordModel)} WHERE organization_id = :org",
                f"DELETE FROM {DEFINITIONS}.workflow_method_pins WHERE organization_id = :org",
                f"DELETE FROM {APP}.workflow_state_machines WHERE organization_id = :org",
                f"DELETE FROM {DEFINITIONS}.method_library_method_version_fields WHERE organization_id = :org",
                f"DELETE FROM {DEFINITIONS}.method_library_method_versions WHERE organization_id = :org",
                f"DELETE FROM {DEFINITIONS}.method_library_methods WHERE organization_id = :org",
                f"DELETE FROM {DEFINITIONS}.method_library_org_counters WHERE organization_id = :org",
                f"DELETE FROM {DEFINITIONS}.field_library_field_versions WHERE organization_id = :org",
                f"DELETE FROM {DEFINITIONS}.field_library_fields WHERE organization_id = :org",
                f"DELETE FROM {DEFINITIONS}.entity_type_schema WHERE organization_id = :org",
                f"DELETE FROM {DEFINITIONS}.entity_type_relations WHERE organization_id = :org",
                f"DELETE FROM {DEFINITIONS}.entity_types WHERE organization_id = :org",
            ):
                session.execute(text(statement), {"org": ORG_A})
            session.commit()
        finally:
            session.close()

    _purge()
    yield
    _purge()


# ── Builders ──────────────────────────────────────────────────────────────────


def _entity_type(entities_db, name: str) -> str:
    return entities_db.create_entity_type(
        EntityTypeCreateRequest(organization_id=ORG_A, name=name)
    ).entity_type_id


def _declaration(
    entities_db,
    *,
    from_entity_type_id: str,
    to_entity_type_id: str,
    relation_type: RelationType = RelationType.REFERENCE,
    relation_metadata: dict | None = None,
) -> str:
    return entities_db.create_entity_relation_declaration(
        EntityRelationDeclarationCreateRequest(
            organization_id=ORG_A,
            from_entity_type_id=from_entity_type_id,
            to_entity_type_id=to_entity_type_id,
            relation_type=relation_type,
            relation_metadata=relation_metadata or {},
        ),
        default_relation_type=relation_type.value,
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


def _make_field(field_service, *, field_key: str | None = None) -> tuple[str, str]:
    suffix = uuid.uuid4().hex[:8]
    key = field_key or f"field_{suffix}"
    created = field_service.create_field(
        organization_id=ORG_A,
        name=f"Field {suffix}",
        field_key=key,
        field_type="text",
        description=None,
        settings={},
        created_by="user-a",
    )
    return created.identity.library_field_id, created.identity.field_key


def _make_method(method_service, *, name: str, fields: list[MethodFieldInput]):
    return method_service.create_method_with_fields(
        organization_id=ORG_A,
        name=name,
        description=None,
        category_id=None,
        field_inputs=fields,
        created_by="user-a",
    )


def _inherited_input(
    library_field_id: str, *, source_entity_type: str, source_field_key: str, position: int = 0
) -> MethodFieldInput:
    return MethodFieldInput(
        library_field_id=library_field_id,
        label="Field",
        placeholder=None,
        required=False,
        position=position,
        ownership=FieldOwnership.INHERITED.value,
        source_entity_type=source_entity_type,
        source_field_key=source_field_key,
    )


def _plain_input(library_field_id: str, *, position: int = 0) -> MethodFieldInput:
    return MethodFieldInput(
        library_field_id=library_field_id, label="Field", required=False, position=position
    )


def _definition(entity_type: str, states: list[State], machine_key: str) -> StateMachineDefinition:
    return StateMachineDefinition(
        machine_key=machine_key,
        name="Ownership Machine",
        entity_type=entity_type,
        entity_schema=EntitySchema(entity_type=entity_type, fields=[]),
        states=states,
        initial_state="start",
        transitions=[
            Transition(
                key="start_to_end", trigger="complete", label="Complete", to_state="end",
                **{"from": "start"},
            )
        ],
    )


def _states(method_refs: list[MethodRef]) -> list[State]:
    return [
        State(name="start", tags=["initial"], order=1, method_refs=method_refs),
        State(name="end", tags=["terminal"], order=2),
    ]


def _draft(workflow_db, entity_type: str) -> tuple[str, str, str]:
    machine_name = f"ownership_{uuid.uuid4().hex[:8]}"
    machine_key = machine_name
    record = workflow_db.create_state_machine_draft(
        organization_id=ORG_A,
        machine_name=machine_name,
        machine_key=machine_key,
        definition=_definition(entity_type, _states([]), machine_key).model_dump(mode="json"),
        created_by="user-a",
    )
    return record.id, machine_name, machine_key


def _publish(manager, row_id: str, definition: StateMachineDefinition):
    return manager.publish_workflow_for_actor(
        ACTOR_A, row_id, WorkflowPublishRequest(definition=definition)
    )


def _record(entities_service_manager, *, entity_type_id: str, data: dict, sources: list[str] | None = None):
    return entities_service_manager.create_entity_record_for_actor(
        ACTOR_A,
        EntityRecordCreateRequest(
            organization_id=ORG_A,
            entity_type_id=entity_type_id,
            data=data,
            **({"source_entity_ids": sources} if sources else {}),
        ),
    )


def _column_info(entities_db_service_manager) -> list[tuple[str, str]]:
    session = entities_db_service_manager.postgres_db_service().get_db_session()
    try:
        return [
            tuple(row)
            for row in session.execute(
                text(
                    "SELECT data_type, character_maximum_length::text "
                    "FROM information_schema.columns "
                    "WHERE table_schema = :schema AND table_name = :table AND column_name = 'ownership'"
                ),
                {"schema": DEFINITIONS, "table": "method_library_method_version_fields"},
            ).all()
        ]
    finally:
        session.close()


# ── Migration discipline ──────────────────────────────────────────────────────


def test_migration_is_reversible_and_idempotent(entities_db_service_manager, monkeypatch) -> None:
    """upgrade (no-op if present) -> downgrade -> upgrade -> upgrade again.

    Runs against the same Postgres the app boots against, so the column is
    restored in a `finally` whatever happens in between. A second `upgrade()`
    must be a clean no-op: that is the `IF NOT EXISTS` doing its job.
    """
    monkeypatch.setenv("POSTGRES_APP_SCHEMA", APP)
    spec = importlib.util.spec_from_file_location("ownership_migration", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = entities_db_service_manager.postgres_db_service().engine

    class FakeOp:
        """The only surface the migration touches: `op.get_bind()`."""

        def __init__(self, connection) -> None:
            self._connection = connection

        def get_bind(self):
            return self._connection

    def run(fn) -> None:
        with engine.begin() as connection:
            monkeypatch.setattr(migration, "op", FakeOp(connection))
            fn()

    try:
        run(migration.upgrade)
        assert _column_info(entities_db_service_manager) == [("character varying", "32")]

        run(migration.downgrade)
        assert _column_info(entities_db_service_manager) == []

        run(migration.upgrade)
        assert _column_info(entities_db_service_manager) == [("character varying", "32")]

        # Double-run: must not raise and must leave exactly one column.
        run(migration.upgrade)
        assert _column_info(entities_db_service_manager) == [("character varying", "32")]
    finally:
        run(migration.upgrade)


# ── Request model ─────────────────────────────────────────────────────────────


def test_request_refuses_inherited_without_a_source() -> None:
    with pytest.raises(ValueError, match="requires source_entity_type and source_field_key"):
        MethodFieldInput(library_field_id="f", ownership="inherited")


def test_request_refuses_unknown_ownership_values() -> None:
    with pytest.raises(ValueError, match="ownership must be one of"):
        MethodFieldInput(library_field_id="f", ownership="borrowed")


def test_request_refuses_both_mechanisms_on_one_field() -> None:
    with pytest.raises(ValueError, match="cannot set both inherit_from and ownership"):
        MethodFieldInput(
            library_field_id="f",
            ownership="inherited",
            source_entity_type="Client",
            source_field_key="name",
            inherit_from="Client.name",
        )


def test_request_normalises_ownership_case() -> None:
    field = MethodFieldInput(
        library_field_id="f",
        ownership="  INHERITED ",
        source_entity_type="Client",
        source_field_key="name",
    )
    assert field.ownership == FieldOwnership.INHERITED.value


def test_request_owned_needs_no_source() -> None:
    assert MethodFieldInput(library_field_id="f", ownership="owned").ownership == "owned"


# ── Publish-time guard and non-projection ─────────────────────────────────────


def test_publish_blocks_when_no_relation_is_declared(
    manager, workflow_db, method_service, field_service, entities_db
) -> None:
    target_name = f"Qual_{uuid.uuid4().hex[:8]}"
    _entity_type(entities_db, target_name)
    field_id, _ = _make_field(field_service)
    identity, _ = _make_method(
        method_service,
        name="Client Details",
        fields=[
            _inherited_input(
                field_id, source_entity_type=f"NoSuchClient_{uuid.uuid4().hex[:8]}", source_field_key="name"
            )
        ],
    )
    row_id, _, machine_key = _draft(workflow_db, target_name)

    with pytest.raises(ValidationError, match="no relation is declared"):
        _publish(
            manager,
            row_id,
            _definition(target_name, _states([MethodRef(method_id=identity.method_id)]), machine_key),
        )


def test_publish_succeeds_marks_the_field_inherited_and_writes_no_relation_metadata(
    manager, workflow_db, method_service, field_service, entities_db, entities_db_service_manager
) -> None:
    client_name = f"Client_{uuid.uuid4().hex[:8]}"
    target_name = f"Qual_{uuid.uuid4().hex[:8]}"
    client_id = _entity_type(entities_db, client_name)
    target_id = _entity_type(entities_db, target_name)
    declaration_id = _declaration(entities_db, from_entity_type_id=client_id, to_entity_type_id=target_id)
    assert _relation_metadata(entities_db_service_manager, declaration_id) == {}

    field_id, field_key = _make_field(field_service)
    identity, _ = _make_method(
        method_service,
        name="Client Details",
        fields=[_inherited_input(field_id, source_entity_type=client_name, source_field_key="name")],
    )
    row_id, _, machine_key = _draft(workflow_db, target_name)

    published = _publish(
        manager,
        row_id,
        _definition(target_name, _states([MethodRef(method_id=identity.method_id)]), machine_key),
    )

    pinned = next(f for f in published.state_machine.definition.entity_schema.fields if f.field == field_key)
    assert pinned.ownership == FieldOwnership.INHERITED.value
    assert pinned.source == {"context_entity_type": client_name, "context_field": "name"}
    assert pinned.editable is False
    # The whole point: nothing was escalated to the entity type.
    assert _relation_metadata(entities_db_service_manager, declaration_id) == {}


# ── Runtime resolution: per-block, and the untouched blanket path ─────────────


def _client_and_target(entities_db, *, relation_type=RelationType.REFERENCE, relation_metadata=None):
    client_name = f"Client_{uuid.uuid4().hex[:8]}"
    target_name = f"Qual_{uuid.uuid4().hex[:8]}"
    client_id = _entity_type(entities_db, client_name)
    target_id = _entity_type(entities_db, target_name)
    declaration_id = _declaration(
        entities_db,
        from_entity_type_id=client_id,
        to_entity_type_id=target_id,
        relation_type=relation_type,
        relation_metadata=relation_metadata,
    )
    return client_name, client_id, target_name, target_id, declaration_id


def test_inherited_field_resolves_only_for_records_in_the_opted_in_workflow(
    manager, workflow_db, method_service, field_service, entities_db, entities_service_manager
) -> None:
    client_name, client_id, target_name, target_id, _ = _client_and_target(entities_db)
    field_id, field_key = _make_field(field_service)
    identity, _ = _make_method(
        method_service,
        name="Client Details",
        fields=[_inherited_input(field_id, source_entity_type=client_name, source_field_key="name")],
    )
    row_id, machine_name, machine_key = _draft(workflow_db, target_name)
    _publish(
        manager,
        row_id,
        _definition(target_name, _states([MethodRef(method_id=identity.method_id)]), machine_key),
    )

    client = _record(
        entities_service_manager,
        entity_type_id=client_id,
        data={"identifier": "acme", "name": "Acme Laboratories"},
    )
    enrolled = _record(
        entities_service_manager,
        entity_type_id=target_id,
        data={"identifier": "qual-1"},
        sources=[client.entity_id],
    )
    unenrolled = _record(
        entities_service_manager,
        entity_type_id=target_id,
        data={"identifier": "qual-2"},
        sources=[client.entity_id],
    )
    manager.enroll_entity_for_actor(ACTOR_A, machine_name, enrolled.entity_id)

    resolved_enrolled = entities_db.resolve_inherited_fields(
        organization_id=ORG_A, entity_type_id=target_id, entity_id=enrolled.entity_id
    )
    resolved_unenrolled = entities_db.resolve_inherited_fields(
        organization_id=ORG_A, entity_type_id=target_id, entity_id=unenrolled.entity_id
    )

    # Same type, same client link. Only the record whose workflow pins the
    # opted-in block gets the value - that is the scoping this exists for.
    assert resolved_enrolled.get(field_key) == "Acme Laboratories"
    assert field_key not in resolved_unenrolled


def test_batch_resolver_returns_the_per_block_field_when_requested(
    manager, workflow_db, method_service, field_service, entities_db, entities_service_manager
) -> None:
    client_name, client_id, target_name, target_id, _ = _client_and_target(entities_db)
    field_id, field_key = _make_field(field_service)
    identity, _ = _make_method(
        method_service,
        name="Client Details",
        fields=[_inherited_input(field_id, source_entity_type=client_name, source_field_key="name")],
    )
    row_id, machine_name, machine_key = _draft(workflow_db, target_name)
    _publish(
        manager,
        row_id,
        _definition(target_name, _states([MethodRef(method_id=identity.method_id)]), machine_key),
    )
    client = _record(entities_service_manager, entity_type_id=client_id, data={"identifier": "acme", "name": "Acme"})
    enrolled = _record(
        entities_service_manager, entity_type_id=target_id, data={"identifier": "q1"}, sources=[client.entity_id]
    )
    unenrolled = _record(
        entities_service_manager, entity_type_id=target_id, data={"identifier": "q2"}, sources=[client.entity_id]
    )
    manager.enroll_entity_for_actor(ACTOR_A, machine_name, enrolled.entity_id)

    records = entities_db.list_entity_records_by_ids(
        organization_id=ORG_A, entity_ids={enrolled.entity_id, unenrolled.entity_id}
    )
    assert len(records) == 2
    resolved = entities_db.resolve_inherited_fields_for_records(
        organization_id=ORG_A, records=records, field_names={field_key}
    )

    assert resolved.get(enrolled.entity_id, {}).get(field_key) == "Acme"
    assert field_key not in resolved.get(unenrolled.entity_id, {})


def test_writes_to_a_per_block_inherited_field_are_refused_only_on_enrolled_records(
    manager, workflow_db, method_service, field_service, entities_db, entities_service_manager
) -> None:
    """The write guard is scoped to the record, not the type.

    A record enrolled in the workflow that pins the field must get the same 403
    a relation_metadata target gets — otherwise a client could persist a value
    the read overlay silently masks. A record of the same type that is NOT
    enrolled there owns the key and may still write it, exactly as before.
    """
    client_name, client_id, target_name, target_id, _ = _client_and_target(entities_db)
    field_id, field_key = _make_field(field_service)
    identity, _ = _make_method(
        method_service,
        name="Client Details",
        fields=[_inherited_input(field_id, source_entity_type=client_name, source_field_key="name")],
    )
    row_id, machine_name, machine_key = _draft(workflow_db, target_name)
    _publish(
        manager,
        row_id,
        _definition(target_name, _states([MethodRef(method_id=identity.method_id)]), machine_key),
    )
    client = _record(entities_service_manager, entity_type_id=client_id, data={"identifier": "acme", "name": "Acme"})
    enrolled = _record(
        entities_service_manager, entity_type_id=target_id, data={"identifier": "q1"}, sources=[client.entity_id]
    )
    unenrolled = _record(
        entities_service_manager, entity_type_id=target_id, data={"identifier": "q2"}, sources=[client.entity_id]
    )
    manager.enroll_entity_for_actor(ACTOR_A, machine_name, enrolled.entity_id)

    with pytest.raises(AuthorizationError, match=field_key):
        entities_service_manager.update_entity_record_for_actor(
            ACTOR_A, enrolled.entity_id, EntityRecordUpdateRequest(data={field_key: "tampered"})
        )
    # An owned sibling key on the same enrolled record still writes.
    entities_service_manager.update_entity_record_for_actor(
        ACTOR_A, enrolled.entity_id, EntityRecordUpdateRequest(data={"notes": "fine"})
    )
    # The unenrolled record owns the key.
    updated = entities_service_manager.update_entity_record_for_actor(
        ACTOR_A, unenrolled.entity_id, EntityRecordUpdateRequest(data={field_key: "mine"})
    )
    assert updated.data.get(field_key) == "mine"


def test_blanket_relation_metadata_resolution_is_unchanged(entities_db, entities_service_manager) -> None:
    """The pre-existing mechanism, with no workflow or enrollment anywhere.

    A declaration carrying an explicit relation_metadata mapping must resolve
    exactly as it did before this change: for every record of the type, with
    nothing pinned and nothing enrolled. This is the fallback the non-goals
    protect.
    """
    client_name = f"Client_{uuid.uuid4().hex[:8]}"
    target_name = f"Opp_{uuid.uuid4().hex[:8]}"
    client_id = _entity_type(entities_db, client_name)
    target_id = _entity_type(entities_db, target_name)
    _declaration(
        entities_db,
        from_entity_type_id=client_id,
        to_entity_type_id=target_id,
        relation_metadata={f"{client_name}.region": f"{target_name}.account_region"},
    )
    client = _record(
        entities_service_manager, entity_type_id=client_id, data={"identifier": "acct", "region": "EMEA"}
    )
    target = _record(
        entities_service_manager, entity_type_id=target_id, data={"identifier": "opp-1"}, sources=[client.entity_id]
    )

    resolved = entities_db.resolve_inherited_fields(
        organization_id=ORG_A, entity_type_id=target_id, entity_id=target.entity_id
    )
    assert resolved.get("account_region") == "EMEA"

    inheritable = entities_db.inheritable_field_names_by_type(
        organization_id=ORG_A, entity_type_ids={target_id}
    )
    assert "account_region" in inheritable.get(target_id, set())


def test_inheritable_field_names_include_per_block_fields_from_active_workflows(
    manager, workflow_db, method_service, field_service, entities_db
) -> None:
    """A read-policy condition on a per-block inherited field must be
    row-scanned, not pushed to SQL against a stored value that is not there."""
    client_name, _, target_name, target_id, _ = _client_and_target(entities_db)
    field_id, field_key = _make_field(field_service)
    identity, _ = _make_method(
        method_service,
        name="Client Details",
        fields=[_inherited_input(field_id, source_entity_type=client_name, source_field_key="name")],
    )
    row_id, _, machine_key = _draft(workflow_db, target_name)

    before = entities_db.inheritable_field_names_by_type(organization_id=ORG_A, entity_type_ids={target_id})
    assert field_key not in before.get(target_id, set())

    _publish(
        manager,
        row_id,
        _definition(target_name, _states([MethodRef(method_id=identity.method_id)]), machine_key),
    )

    after = entities_db.inheritable_field_names_by_type(organization_id=ORG_A, entity_type_ids={target_id})
    assert field_key in after.get(target_id, set())


def test_a_plain_field_publishes_exactly_as_before(
    manager, workflow_db, method_service, field_service, entities_db
) -> None:
    target_name = f"Plain_{uuid.uuid4().hex[:8]}"
    _entity_type(entities_db, target_name)
    field_id, field_key = _make_field(field_service)
    identity, _ = _make_method(method_service, name="Plain", fields=[_plain_input(field_id)])
    row_id, _, machine_key = _draft(workflow_db, target_name)

    published = _publish(
        manager,
        row_id,
        _definition(target_name, _states([MethodRef(method_id=identity.method_id)]), machine_key),
    )
    pinned = next(f for f in published.state_machine.definition.entity_schema.fields if f.field == field_key)
    assert pinned.ownership is None
    assert pinned.source is None
