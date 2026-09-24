"""Definition-level cell-calc validation.

Constructs EntityField, so it needs the Python 3.12 backend env (the local 3.11
enum-membership bug prevents EntityField construction). Run in the Docker
backend container:
    docker compose -f docker-compose.local.yml exec -T modular-backend \
        python -m pytest tests/test_calc_workflow_validation.py -v
"""
from __future__ import annotations

from types import SimpleNamespace

from workflow_manager_factory import NoActiveFormsManager

from workflow.models.interface import EntityField, ValidationIssueCode
from workflow.services import EntitySchemaService


def _definition(field_dicts: list[dict]) -> SimpleNamespace:
    fields = [EntityField(**fd) for fd in field_dicts]
    return SimpleNamespace(entity_schema=SimpleNamespace(fields=fields))


def test_cell_calc_bad_ref_rejected() -> None:
    fields = [{
        "field": "grid", "type": "json",
        "table_config": {"row_mode": "fixed",
            "columns": [{"id": "c1", "type": "number"}],
            "rows": [{"id": "r1", "cell_config": {"c1": {"calc": {"t": "cell", "row": "r1", "col": "nope"}}}}]},
    }]
    issues = EntitySchemaService(NoActiveFormsManager())._validate_calc_fields(_definition(fields))
    assert any(i.code == ValidationIssueCode.CALC_INVALID_REF for i in issues)


def test_cell_calc_cycle_rejected() -> None:
    fields = [{
        "field": "grid", "type": "json",
        "table_config": {"row_mode": "fixed",
            "columns": [{"id": "x", "type": "number"}, {"id": "y", "type": "number"}],
            "rows": [{"id": "r1", "cell_config": {
                "x": {"calc": {"t": "cell", "row": "r1", "col": "y"}},
                "y": {"calc": {"t": "cell", "row": "r1", "col": "x"}},
            }}]},
    }]
    issues = EntitySchemaService(NoActiveFormsManager())._validate_calc_fields(_definition(fields))
    assert any(i.code == ValidationIssueCode.CALC_CYCLE for i in issues)


def test_column_calc_cycle_rejected() -> None:
    fields = [{
        "field": "grid", "type": "json",
        "table_config": {"row_mode": "dynamic",
            "columns": [
                {"id": "a", "type": "number", "calc": {"t": "col", "col": "b"}},
                {"id": "b", "type": "number", "calc": {"t": "col", "col": "a"}},
            ]},
    }]
    issues = EntitySchemaService(NoActiveFormsManager())._validate_calc_fields(_definition(fields))
    assert any(i.code == ValidationIssueCode.CALC_CYCLE for i in issues)


def test_cell_calc_self_reference_rejected() -> None:
    fields = [{
        "field": "grid", "type": "json",
        "table_config": {"row_mode": "fixed",
            "columns": [{"id": "x", "type": "number"}, {"id": "y", "type": "number"}],
            "rows": [{"id": "r1", "cell_config": {"x": {"calc": {"t": "binary", "op": "add",
                "left": {"t": "cell", "row": "r1", "col": "x"},
                "right": {"t": "cell", "row": "r1", "col": "y"}}}}}]},
    }]
    issues = EntitySchemaService(NoActiveFormsManager())._validate_calc_fields(_definition(fields))
    assert any(i.code == ValidationIssueCode.CALC_CYCLE for i in issues)


def test_cell_calc_valid_passes() -> None:
    fields = [{
        "field": "grid", "type": "json",
        "table_config": {"row_mode": "fixed",
            "columns": [{"id": "a", "type": "number"}, {"id": "b", "type": "number"}, {"id": "s", "type": "number"}],
            "rows": [{"id": "r1", "cell_config": {"s": {"calc": {"t": "binary", "op": "add",
                "left": {"t": "cell", "row": "r1", "col": "a"},
                "right": {"t": "cell", "row": "r1", "col": "b"}}}}}]},
    }]
    issues = EntitySchemaService(NoActiveFormsManager())._validate_calc_fields(_definition(fields))
    assert issues == []
