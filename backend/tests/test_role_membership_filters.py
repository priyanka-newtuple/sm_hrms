"""Membership read permissions must agree in Python and real PostgreSQL queries."""

from types import SimpleNamespace

import pytest
from sqlalchemy import column, select, values
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import visitors
from test_workflow_module import workflow_manager as workflow_manager

from common.condition_values import parse_membership_values
from common.protocols import EntityConditionSpec, resolve_and_compare
from exceptions import ValidationError
from roles.manager import RolesServiceManager
from roles.models.request import EntityPermissionCreate
from workflow.db_models import EntityRecordModel, WorkflowModelService

# Expected inclusion, exclusion. Empty/unsupported records satisfy neither operator.
CASES = [
    ({"field": "alpha"}, True, False),
    ({"field": "beta"}, True, False),
    ({"field": "gamma"}, False, True),
    ({"field": "Alpha"}, False, True),
    ({"field": "alphabet"}, False, True),
    ({"field": " alpha "}, False, True),
    ({"field": "alpha,beta"}, False, True),
    ({"field": ["alpha", "gamma"]}, True, False),
    ({"field": ["gamma", "beta"]}, True, False),
    ({"field": ["gamma", "delta"]}, False, True),
    ({"field": ["alpha", "alpha"]}, True, False),
    ({"field": [None, "", "beta"]}, True, False),
    ({"field": [None, "", "gamma"]}, False, True),
    ({}, False, False),
    ({"field": None}, False, False),
    ({"field": ""}, False, False),
    ({"field": []}, False, False),
    ({"field": [None, ""]}, False, False),
    ({"field": {}}, False, False),
    ({"field": {"value": "alpha"}}, False, False),
    ({"field": [["alpha"]]}, False, False),
    ({"field": ["alpha", {}]}, False, False),
    ({"field": 0}, False, True),
    ({"field": False}, False, True),
]


def sql_results(engine, condition, records):
    predicate = WorkflowModelService.read_condition_expression(condition)
    source = values(column("id"), column("data", JSONB), name="samples").data(
        list(enumerate(records))
    )
    expression = visitors.replacement_traverse(
        predicate,
        {},
        lambda node: source.c.data if node.compare(EntityRecordModel.data.expression) else None,
    )
    with engine.connect() as connection:
        return dict(connection.execute(select(source.c.id, expression).select_from(source)).all())


@pytest.mark.parametrize("operator,index", [("in", 1), ("not_in", 2)])
@pytest.mark.parametrize("input_value", ["alpha,beta", " alpha, beta ", ",alpha,, beta,alpha, "])
def test_membership_matrix(entities_db_service_manager, operator, index, input_value):
    condition = EntityConditionSpec("field", operator, input_value)
    engine = entities_db_service_manager.postgres_db_service().engine
    actual = sql_results(engine, condition, [case[0] for case in CASES])
    for row_id, case in enumerate(CASES):
        assert resolve_and_compare(condition, case[0]) is case[index], case
        assert bool(actual[row_id]) is case[index], case


@pytest.mark.parametrize("operator", ["in", "not_in"])
@pytest.mark.parametrize("input_value", ["", " , , "])
def test_invalid_legacy_membership_never_grants_access(
    entities_db_service_manager, operator, input_value
):
    condition = EntityConditionSpec("field", operator, input_value)
    records = [{"field": "alpha"}, {"field": ["alpha"]}, {}]
    assert not any(resolve_and_compare(condition, data) for data in records)
    assert not any(
        sql_results(
            entities_db_service_manager.postgres_db_service().engine, condition, records
        ).values()
    )


@pytest.mark.parametrize("operator", ["in", "not_in"])
@pytest.mark.parametrize("compound", [False, True])
def test_save_rejects_empty_membership_lists(operator, compound):
    manager = RolesServiceManager(
        SimpleNamespace(get_entity_type_schema_fields=lambda *_: [{"id": "field"}])
    )
    condition = {
        "entity_field": "field",
        "operator": operator,
        "condition_value": " , , ",
        "value_source": "LITERAL",
    }
    payload = {"read_filter": {"conditions": [condition]}} if compound else condition
    with pytest.raises(ValidationError, match="non-empty comma-separated"):
        manager._validate_entity_condition(
            None, "org", EntityPermissionCreate(entity_type="Test", action="view", **payload)
        )


@pytest.mark.parametrize("operator", ["==", "!="])
@pytest.mark.parametrize("compound", [False, True])
def test_save_rejects_comma_in_scalar_equality(operator, compound):
    manager = RolesServiceManager(
        SimpleNamespace(get_entity_type_schema_fields=lambda *_: [{"id": "field"}])
    )
    condition = {
        "entity_field": "field",
        "operator": operator,
        "condition_value": "alpha,beta",
        "value_source": "LITERAL",
    }
    payload = {"read_filter": {"conditions": [condition]}} if compound else condition
    with pytest.raises(ValidationError, match="Commas are not allowed with 'Equals' or 'Not equals'"):
        manager._validate_entity_condition(
            None, "org", EntityPermissionCreate(entity_type="Test", action="view", **payload)
        )


def test_tokens_are_cached_per_compiled_policy():
    condition = EntityConditionSpec("field", "in", " a, b,, a ")
    assert condition.membership_values == frozenset({"a", "b"})
    assert condition.membership_values is condition.membership_values
    assert parse_membership_values(None) == frozenset()


@pytest.mark.parametrize("operator", ["in", "not_in"])
def test_boolean_numeric_and_unicode_membership(entities_db_service_manager, operator):
    condition = EntityConditionSpec(
        "field", operator, "True, 42, 1.5, café, 東京, O'Reilly, a%b, a_b"
    )
    records = [
        {"field": value}
        for value in [
            True,
            False,
            42,
            0,
            1.5,
            "café",
            "東京",
            "O'Reilly",
            "a%b",
            "a_b",
            "axb",
            [42, "other"],
            [False, "other"],
        ]
    ]
    engine = entities_db_service_manager.postgres_db_service().engine
    actual = sql_results(engine, condition, records)
    for index, data in enumerate(records):
        assert bool(actual[index]) == resolve_and_compare(condition, data), data


@pytest.mark.parametrize("operator", ["in", "not_in"])
def test_numeric_exponents_match_without_changing_text_comparisons(
    entities_db_service_manager, operator
):
    condition = EntityConditionSpec("field", operator, "1e-7, 1e20, 42.0, -0.0")
    cases = [
        (1e-7, True),
        (1e20, True),
        (42, True),
        (42.0, True),
        (0, True),
        ("42", False),
        ("42.0", True),
        ("0.0000001", False),
        ("1e-7", True),
        ([1e-7, "other"], True),
        ([43, "other"], False),
    ]
    records = [{"field": value} for value, _ in cases]
    actual = sql_results(
        entities_db_service_manager.postgres_db_service().engine, condition, records
    )
    for index, (value, included) in enumerate(cases):
        expected = included if operator == "in" else not included
        assert resolve_and_compare(condition, {"field": value}) is expected
        assert bool(actual[index]) is expected


@pytest.mark.parametrize("first,second", [("AND", "OR"), ("OR", "AND")])
def test_membership_with_mixed_connectors(entities_db_service_manager, first, second):
    condition = EntityConditionSpec.from_permission(
        SimpleNamespace(
            read_filter={
                "conditions": [
                    {"entity_field": "tags", "operator": "in", "condition_value": "alpha, beta"},
                    {
                        "entity_field": "status",
                        "operator": "not_in",
                        "condition_value": "Closed, Archived",
                        "conjunction": first,
                    },
                    {
                        "entity_field": "owner",
                        "operator": "==",
                        "condition_value": "Sam",
                        "conjunction": second,
                    },
                ]
            }
        )
    )
    from itertools import product

    records = [
        {"tags": tags, "status": status, "owner": owner}
        for tags, status, owner in product(
            [[], ["alpha"], ["gamma"], ["alpha", "gamma"]],
            [None, "Open", "Closed", ["Open", "Archived"]],
            ["Sam", "Alex"],
        )
    ]
    actual = sql_results(
        entities_db_service_manager.postgres_db_service().engine, condition, records
    )
    for index, record in enumerate(records):
        a = "alpha" in record["tags"]
        b = record["status"] == "Open"
        c = record["owner"] == "Sam"
        expected = (a and b) or c if first == "AND" else a or (b and c)
        assert resolve_and_compare(condition, record) is expected, record
        assert bool(actual[index]) is expected, record


@pytest.mark.parametrize("operator", ["in", "not_in"])
def test_membership_filters_real_workflow_pages_and_identifier_options(workflow_manager, operator):
    from test_workflow_module import _admin_actor, _register_entity_type

    from entities.models.request import EntityRecordCreateRequest
    from workflow.models.interface import EntitySchema, State, StateMachineDefinition
    from workflow.models.request import StateMachineCreateRequest

    type_name = "membership_test"
    type_id = _register_entity_type(workflow_manager, name=type_name)
    definition = StateMachineDefinition(
        machine_key="membership",
        name="Membership",
        description="",
        entity_type=type_name,
        entity_schema=EntitySchema(entity_type=type_name, fields=[]),
        states=[State(name="active", tags=["initial"], order=1)],
        initial_state="active",
        transitions=[],
    )
    workflow_manager.workflow_db.create_state_machine_published(
        StateMachineCreateRequest(
            machine_name="membership", version=1, is_active=True, definition=definition
        ),
        organization_id="test-org-1",
    )
    records = {
        "R1": ["alpha", "gamma"],
        "R2": "beta",
        "R3": ["delta", "gamma"],
        "R4": "delta",
        "R5": [],
        "R6": None,
        "R7": "",
    }
    for identifier, value in records.items():
        record = workflow_manager.entities_service_manager.create_entity_record(
            EntityRecordCreateRequest(
                organization_id="test-org-1",
                entity_type_id=type_id,
                data={"identifier": identifier, "field": value},
            )
        )
        workflow_manager.enroll_entity_for_actor(
            _admin_actor(), machine_name="membership", entity_id=record.entity_id
        )
    args = {
        "organization_id": "test-org-1",
        "machine_name": "membership",
        "read_conditions_by_type": {
            type_id: [EntityConditionSpec("field", operator, " alpha, beta, ")]
        },
    }
    expected = {"R1", "R2"} if operator == "in" else {"R3", "R4"}
    rows = workflow_manager.workflow_db.list_enrollment_summary_rows(**args, limit=100)
    assert {row.entity_data["identifier"] for row in rows} == expected
    pages = [
        workflow_manager.workflow_db.list_enrollment_summary_rows(**args, offset=index, limit=1)
        for index in range(3)
    ]
    assert {page[0].entity_data["identifier"] for page in pages if page} == expected
    assert pages[2] == []
    assert (
        set(workflow_manager.workflow_db.list_enrollment_summary_identifier_options(**args))
        == expected
    )
