from __future__ import annotations

import pytest
from workflow_manager_factory import NoActiveFormsManager

from exceptions import ValidationError
from workflow.models.interface import EntityField
from workflow.services import EntitySchemaService


def _table_config() -> dict:
    return {
        "row_mode": "fixed",
        "min_rows": 1,
        "columns": [
            {"id": "total_revenues", "label": "Total Revenues", "type": "currency", "required": True},
            {"id": "interstate_percent", "label": "Interstate", "type": "percent"},
            {"id": "notes", "label": "Notes", "type": "text"},
        ],
        "rows": [{"id": "line_303_1", "line": "303.1", "label": "PICC charges to IXCs"}],
    }


def _dynamic_table_config(**overrides: object) -> dict:
    config = {
        "row_mode": "dynamic",
        "columns": [
            {"id": "description", "label": "Description", "type": "text", "required": True},
            {"id": "amount", "label": "Amount", "type": "number"},
        ],
    }
    config.update(overrides)
    return config


def test_entity_field_accepts_table_config_on_json_fields() -> None:
    field = EntityField(
        field="block_3_revenues",
        type="json",
        required=True,
        table_config=_table_config(),
    )

    assert field.table_config is not None
    assert field.table_config["row_mode"] == "fixed"


def test_entity_field_rejects_table_config_on_non_json_fields() -> None:
    with pytest.raises(ValueError, match="table_config is only supported"):
        EntityField(field="bad_table", type="string", table_config=_table_config())


def test_table_value_validation_accepts_fixed_rows() -> None:
    EntitySchemaService(NoActiveFormsManager())._validate_table_value(
        "block_3_revenues",
        [
            {
                "_row_id": "line_303_1",
                "_line": "303.1",
                "_label": "PICC charges to IXCs",
                "total_revenues": 12500,
                "interstate_percent": 80,
                "notes": "Reviewed",
            }
        ],
        _table_config(),
    )


def test_table_value_validation_rejects_missing_required_cell() -> None:
    with pytest.raises(ValidationError, match="Total Revenues"):
        EntitySchemaService(NoActiveFormsManager())._validate_table_value(
            "block_3_revenues",
            [{"_row_id": "line_303_1", "interstate_percent": 80}],
            _table_config(),
        )


def test_table_value_validation_rejects_wrong_cell_type() -> None:
    with pytest.raises(ValidationError, match="Interstate"):
        EntitySchemaService(NoActiveFormsManager())._validate_table_value(
            "block_3_revenues",
            [{"_row_id": "line_303_1", "total_revenues": 12500, "interstate_percent": "eighty"}],
            _table_config(),
        )


def test_table_value_validation_ignores_blank_dynamic_rows() -> None:
    EntitySchemaService(NoActiveFormsManager())._validate_table_value(
        "line_items",
        [{"_row_id": "row_1", "description": "", "amount": ""}],
        _dynamic_table_config(),
    )


def test_table_value_validation_counts_meaningful_dynamic_rows_for_min_rows() -> None:
    with pytest.raises(ValidationError, match="at least 1"):
        EntitySchemaService(NoActiveFormsManager())._validate_table_value(
            "line_items",
            [{"_row_id": "row_1", "description": "", "amount": ""}],
            _dynamic_table_config(min_rows=1),
        )


def test_table_value_validation_counts_meaningful_dynamic_rows_for_max_rows() -> None:
    EntitySchemaService(NoActiveFormsManager())._validate_table_value(
        "line_items",
        [
            {"_row_id": "row_1", "description": "Filing fee", "amount": 100},
            {"_row_id": "row_2", "description": "", "amount": ""},
        ],
        _dynamic_table_config(max_rows=1),
    )
