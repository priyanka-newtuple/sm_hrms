"""Compound role visibility: API validation, precedence, SQL parity and persistence."""

from itertools import product
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError as ModelValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from common.protocols import (
    EntityConditionSpec,
    record_satisfies_any_condition,
    resolve_and_compare,
)
from exceptions import ValidationError
from roles.db_models import RolesModelService
from roles.manager import RolesServiceManager
from roles.models.request import (
    EntityPermissionCreate,
    RoleCreateRequest,
    RoleDuplicateRequest,
    RoleUpdateRequest,
)
from workflow.db_models import EntityRecordModel, WorkflowModelService


def row(field, conjunction="AND", operator="==", value="yes"):
    return {
        "entity_field": field,
        "conjunction": conjunction,
        "operator": operator,
        "condition_value": value,
        "value_source": "LITERAL",
    }


def spec(rows):
    return EntityConditionSpec.from_permission(SimpleNamespace(read_filter={"conditions": rows}))


@pytest.mark.parametrize("connectors", list(product(["AND", "OR"], repeat=2)))
def test_mixed_precedence(connectors):
    condition = spec([row("a"), row("b", connectors[0]), row("c", connectors[1])])
    for a, b, c in product([False, True], repeat=3):
        if connectors == ("AND", "AND"):
            expected = a and b and c
        elif connectors == ("AND", "OR"):
            expected = (a and b) or c
        elif connectors == ("OR", "AND"):
            expected = a or (b and c)
        else:
            expected = a or b or c
        assert (
            resolve_and_compare(
                condition,
                {"a": "yes" if a else "no", "b": "yes" if b else "no", "c": "yes" if c else "no"},
            )
            == expected
        )
    assert condition.field_names == {"a", "b", "c"}


def test_legacy_missing_fields_and_multiple_roles():
    legacy = EntityConditionSpec.from_permission(
        SimpleNamespace(entity_field="a", operator="==", condition_value="yes")
    )
    compound = spec([row("b", operator="!="), row("c")])
    assert not resolve_and_compare(compound, {"c": "yes"})
    assert not resolve_and_compare(compound, {"b": "", "c": "yes"})
    assert record_satisfies_any_condition([compound, legacy], {"a": "yes"})
    assert record_satisfies_any_condition([], {})
    assert not resolve_and_compare(spec([]), {})


@pytest.mark.parametrize(
    "rows",
    [[], [row("a", "XOR")], [row("a", operator="bad")], [row("a", value="")], [row("a")] * 51],
)
def test_rejects_invalid_expression_shape(rows):
    with pytest.raises(ModelValidationError):
        EntityPermissionCreate(entity_type="Test", action="view", read_filter={"conditions": rows})


def test_validates_every_field_and_rejects_conflicting_or_write_filters():
    manager = RolesServiceManager(
        SimpleNamespace(get_entity_type_schema_fields=lambda *_: [{"id": "a"}])
    )
    for rows in [[row("a"), row("unknown")], [row("a", value="   ")]]:
        with pytest.raises(ValidationError):
            manager._validate_entity_condition(
                None,
                "org",
                EntityPermissionCreate(
                    entity_type="Test", action="view", read_filter={"conditions": rows}
                ),
            )
    for kwargs in [{"action": "edit"}, {"action": "view", "entity_field": "a"}]:
        with pytest.raises(ValidationError):
            manager._validate_entity_condition(
                None,
                "org",
                EntityPermissionCreate(
                    entity_type="Test", read_filter={"conditions": [row("a")]}, **kwargs
                ),
            )


def test_sql_matches_python_for_mixed_conditions(entities_db_service_manager):
    engine = entities_db_service_manager.postgres_db_service().engine
    condition = spec([row("a"), row("b", "OR", "!=", "no"), row("c", "AND", "in", "yes, other")])
    predicate = WorkflowModelService.read_condition_expression(condition)
    # Evaluate the production SQL predicate over inline JSONB records without creating entities.
    from sqlalchemy import column, values
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.sql import visitors

    records = [
        {"a": "yes"},
        {},
        {"b": "", "c": "yes"},
        {"b": "ok", "c": "yes"},
        {"b": True, "c": "other"},
        {"b": "ok", "c": "no"},
    ]
    with engine.connect() as connection:
        for data in records:
            source = values(column("data", JSONB), name="sample").data([(data,)])
            expression = visitors.replacement_traverse(
                predicate,
                {},
                lambda node, source=source: (
                    source.c.data if node.compare(EntityRecordModel.data.expression) else None
                ),
            )
            actual = connection.execute(select(expression).select_from(source)).scalar()
            assert bool(actual) == resolve_and_compare(condition, data)


@pytest.mark.parametrize("operator", ["==", "in", "not_in"])
def test_create_update_duplicate_and_clear_roundtrip(entities_db_service_manager, operator):
    engine = entities_db_service_manager.postgres_db_service().engine
    service = RolesModelService()
    manager = RolesServiceManager(service)
    # The external transaction contains service-level commits; rollback leaves no test roles.
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(connection, join_transaction_mode="create_savepoint") as db:
            permission = EntityPermissionCreate(
                entity_type="Test",
                action="view",
                read_filter={
                    "conditions": [
                        row("a", operator=operator, value="yes, no"),
                        row("b", "OR"),
                        row("c"),
                    ]
                },
            )
            role = service.create_role(
                db,
                "test-org-1",
                RoleCreateRequest(
                    name=f"compound-{uuid4()}",
                    display_name="Compound",
                    entity_permissions=[permission],
                ),
            )
            db.expire_all()
            assert (
                manager._to_role_read(db, role).entity_permissions[0].read_filter
                == permission.read_filter
            )
            copied = service.duplicate_role(
                db,
                role,
                "test-org-1",
                RoleDuplicateRequest(name=f"copy-{uuid4()}", display_name="Copy"),
            )
            assert copied.permissions[0].read_filter == permission.read_filter.model_dump()
            permission.read_filter.conditions[1].conjunction = "AND"
            role = service.update_role(db, role, RoleUpdateRequest(entity_permissions=[permission]))
            assert (
                manager._to_role_read(db, role).entity_permissions[0].read_filter
                == permission.read_filter
            )
            role = service.update_role(
                db,
                role,
                RoleUpdateRequest(
                    entity_permissions=[EntityPermissionCreate(entity_type="Test", action="view")]
                ),
            )
            assert EntityConditionSpec.from_permission(role.permissions[0]) is None
        transaction.rollback()


@pytest.mark.parametrize("unconditional", [False, True])
def test_bulk_and_single_role_policies_agree(unconditional):
    from unittest.mock import Mock

    condition = {"conditions": [row("a"), row("b", "OR"), row("c")]}
    permission = SimpleNamespace(
        permission_key=None,
        entity_type="Test",
        action="view",
        allowed=True,
        entity_field=None,
        operator=None,
        condition_value=None,
        read_filter=condition,
    )
    permissions = [permission]
    if unconditional:
        permissions.append(SimpleNamespace(**{**vars(permission), "read_filter": None}))
    roles = [SimpleNamespace(id="role", is_system=False, permissions=permissions)]
    service = RolesModelService()
    service.get_user_roles_with_permissions = Mock(return_value=roles)
    service.get_field_permissions_for_roles_and_types = Mock(return_value=[])
    db = Mock()
    db.query.return_value.filter.return_value.all.side_effect = [
        [SimpleNamespace(role_id="role")],
        roles,
    ]
    single = service.evaluate_entity_access(db, "user", "org", "Test", "view")
    bulk = RolesServiceManager(service).resolve_entity_read_policies(db, "user", "org", {"Test"})[
        "Test"
    ]
    assert single.allowed
    assert single.conditions == bulk.conditions
    assert bool(single.conditions) is not unconditional


def test_compound_inherited_fields_use_row_scan():
    from test_workflow_module import _access_manager

    from common.protocols import EntityReadPolicy

    condition = spec([row("a"), row("inherited", "OR")])
    manager, services = _access_manager(
        {"application-type": EntityReadPolicy(conditions=[condition])},
        inheritable={"application-type": {"inherited"}},
    )
    access = manager.enrollment_summary.readable_entity_policies(
        {"user_id": "u1"}, "org-1", services
    )
    assert access.needs_row_scan
    assert not access.sql_conditions


def test_first_condition_conjunction_normalised_to_and():
    from roles.models.request import EntityReadFilter

    filter_obj = EntityReadFilter.model_validate(
        {"conditions": [row("a", conjunction="OR"), row("b", conjunction="OR")]}
    )
    assert filter_obj.conditions[0].conjunction == "AND"
    assert filter_obj.conditions[1].conjunction == "OR"


def test_to_role_read_coerces_read_filter_to_model():
    from datetime import datetime
    from roles.models.request import EntityReadFilter

    manager = RolesServiceManager(SimpleNamespace(count_role_assignments=lambda *_: 0))
    mock_perm = SimpleNamespace(
        id="perm-1",
        permission_key=None,
        entity_type="Candidate",
        action="view",
        allowed=True,
        entity_field=None,
        operator=None,
        value_source=None,
        condition_value=None,
        read_filter={"conditions": [row("a")]},
    )
    mock_role = SimpleNamespace(
        id="role-1",
        organization_id="org-1",
        name="custom",
        display_name="Custom",
        description=None,
        is_system=False,
        priority=1,
        color=None,
        permissions=[mock_perm],
        field_permissions=[],
        transition_permissions=[],
        workflow_permissions=[],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    role_read = manager._to_role_read(None, mock_role)
    assert isinstance(role_read.entity_permissions[0].read_filter, EntityReadFilter)

