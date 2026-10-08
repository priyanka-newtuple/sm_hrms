"""Field types the legacy Form -> Method Block migration has to land correctly.

Two gaps the HRMS forms hit:

- A plain JSON field (`proposed`, `participants`) shares the Table / Grid
  catalogue code. Pinning it must not invent a column-less table_config,
  or every save of the field fails "expects table rows".
- The catalogue has no plain-date code, so the migration maps `date` onto
  Date & Time instead of skipping it; `float` lands on the Decimal code.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from method_library.models.interface import MethodVersionField
from workflow.manager import WorkflowServiceManager

CATALOGUE = {"table": ("json", "table")}
COLUMNS = [{"id": "item", "label": "Item", "type": "text"}]


def _table_field(settings: dict) -> MethodVersionField:
    return MethodVersionField(
        id="mvf-1",
        method_version_id="mv-1",
        library_field_id="lf-1",
        field_version_id="fv-1",
        field_key="proposed",
        field_type="table",
        required=True,
        settings=settings,
    )


def _pin(settings: dict):
    return WorkflowServiceManager._entity_field_from_method_field(_table_field(settings), CATALOGUE)


def test_a_plain_json_field_gets_no_table_config():
    field = _pin({"required": True, "nullable": True})

    assert field.type == "json"
    assert field.table_config is None


def test_a_grid_keeps_its_nested_table_config():
    field = _pin({"required": True, "table_config": {"columns": COLUMNS}})

    assert field.table_config == {"columns": COLUMNS}


def test_a_grid_stored_flat_still_keeps_its_columns():
    settings = {"columns": COLUMNS, "row_mode": "dynamic"}

    assert _pin(settings).table_config == settings


@pytest.fixture(scope="module")
def migration():
    path = Path(__file__).resolve().parents[1] / "scripts" / "migrate_forms_to_method_blocks.py"
    spec = importlib.util.spec_from_file_location("migrate_forms_to_method_blocks", path)
    module = importlib.util.module_from_spec(spec)
    # Its dataclasses resolve their module through sys.modules while loading.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BY_ENGINE = {
    "string": "text",
    "datetime": "datetime",
    "int": "integer",
    "float": "decimal",
    "json": "table",
}


@pytest.mark.parametrize(
    ("form_type", "engine_type", "code"),
    [
        ("date", "datetime", "datetime"),
        ("datetime", "datetime", "datetime"),
        ("float", "float", "decimal"),
        ("int", "int", "integer"),
        ("number", "int", "integer"),
        ("json", "json", "table"),
    ],
)
def test_every_hrms_form_type_resolves_to_a_catalogue_code(migration, form_type, engine_type, code):
    assert migration._resolve_code({"type": form_type}, "", BY_ENGINE) == (engine_type, code)


@pytest.mark.parametrize(
    ("value", "ok"), [(50, True), (50.5, True), (0, True), (True, False), ("50", False)]
)
def test_a_decimal_field_accepts_whole_numbers(value, ok):
    from workflow.models.interface import matches_workflow_value

    assert matches_workflow_value("float", value) is ok
