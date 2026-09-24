from __future__ import annotations

from calc.apply import apply_calculations


# --- Base apply behavior (pure; no DB) ---

def test_scalar_arithmetic_overwrites_client_value() -> None:
    fields = [
        {"field": "a", "type": "int"},
        {"field": "b", "type": "int"},
        {"field": "total", "type": "int",
         "calc": {"t": "binary", "op": "add",
                  "left": {"t": "field", "field": "a"},
                  "right": {"t": "field", "field": "b"}}},
    ]
    data = {"a": 3, "b": 4, "total": 999}  # client-sent total is a lie
    out = apply_calculations(fields, data)
    assert out["total"] == 7


def test_aggregate_field_from_table() -> None:
    fields = [
        {"field": "items", "type": "json",
         "table_config": {"columns": [{"id": "amount", "type": "number"}]}},
        {"field": "grand_total", "type": "number",
         "calc": {"t": "agg", "fn": "sum", "table": "items", "column": "amount"}},
    ]
    data = {"items": [{"amount": 2}, {"amount": 3}]}
    out = apply_calculations(fields, data)
    assert out["grand_total"] == 5


def test_per_row_computed_column() -> None:
    fields = [
        {"field": "items", "type": "json",
         "table_config": {"columns": [
             {"id": "qty", "type": "integer"},
             {"id": "price", "type": "number"},
             {"id": "line_total", "type": "number",
              "calc": {"t": "binary", "op": "mul",
                       "left": {"t": "col", "col": "qty"},
                       "right": {"t": "col", "col": "price"}}},
         ]}},
    ]
    data = {"items": [{"qty": 2, "price": 5}, {"qty": 3, "price": 4}]}
    out = apply_calculations(fields, data)
    assert out["items"][0]["line_total"] == 10
    assert out["items"][1]["line_total"] == 12


def test_chained_calc_fields_topo() -> None:
    fields = [
        {"field": "base", "type": "int"},
        {"field": "bonus", "type": "int"},
        {"field": "tax", "type": "int"},
        {"field": "gross", "type": "int",
         "calc": {"t": "binary", "op": "add",
                  "left": {"t": "field", "field": "base"},
                  "right": {"t": "field", "field": "bonus"}}},
        {"field": "net", "type": "int",
         "calc": {"t": "binary", "op": "sub",
                  "left": {"t": "field", "field": "gross"},
                  "right": {"t": "field", "field": "tax"}}},
    ]
    data = {"base": 100, "bonus": 20, "tax": 30}
    out = apply_calculations(fields, data)
    assert out["gross"] == 120
    assert out["net"] == 90


def test_update_merges_partial_over_base() -> None:
    fields = [
        {"field": "a", "type": "int"},
        {"field": "b", "type": "int"},
        {"field": "total", "type": "int",
         "calc": {"t": "binary", "op": "add",
                  "left": {"t": "field", "field": "a"},
                  "right": {"t": "field", "field": "b"}}},
    ]
    base = {"a": 10, "b": 5, "total": 15}
    data = {"a": 20}  # partial update; b unchanged
    out = apply_calculations(fields, data, base=base)
    assert out["total"] == 25


def test_missing_operand_treated_as_zero() -> None:
    # Implemented (amended) semantics: a missing binary operand acts as 0, not null.
    fields = [
        {"field": "a", "type": "int"},
        {"field": "total", "type": "int",
         "calc": {"t": "binary", "op": "add",
                  "left": {"t": "field", "field": "a"},
                  "right": {"t": "field", "field": "b"}}},
    ]
    out = apply_calculations(fields, {"a": 3})
    assert out["total"] == 3


# --- Fixed-row matrix cell calcs (new) ---

def _financials_fields() -> list[dict]:
    def sub(a, b):
        return {"t": "binary", "op": "sub", "left": a, "right": b}
    def add(a, b):
        return {"t": "binary", "op": "add", "left": a, "right": b}
    def cell(r, c):
        return {"t": "cell", "row": r, "col": c}
    return [{
        "field": "financials", "type": "json",
        "table_config": {
            "row_mode": "fixed",
            "columns": [
                {"id": "q1", "type": "currency"},
                {"id": "q2", "type": "currency"},
                {"id": "total", "type": "currency"},
            ],
            "rows": [
                {"id": "rev",  "cell_config": {"total": {"calc": add(cell("rev", "q1"), cell("rev", "q2"))}}},
                {"id": "cost", "cell_config": {"total": {"calc": add(cell("cost", "q1"), cell("cost", "q2"))}}},
                {"id": "profit", "cell_config": {
                    "q1": {"calc": sub(cell("rev", "q1"), cell("cost", "q1"))},
                    "q2": {"calc": sub(cell("rev", "q2"), cell("cost", "q2"))},
                    "total": {"calc": add(cell("profit", "q1"), cell("profit", "q2"))},
                }},
            ],
        },
    }]


def test_matrix_cross_row_and_totals() -> None:
    fields = _financials_fields()
    data = {"financials": [
        {"_row_id": "rev",  "q1": 1000, "q2": 1200},
        {"_row_id": "cost", "q1": 400,  "q2": 500},
        {"_row_id": "profit"},
    ]}
    out = apply_calculations(fields, data)
    rows = {r["_row_id"]: r for r in out["financials"]}
    assert rows["rev"]["total"] == 2200
    assert rows["cost"]["total"] == 900
    assert rows["profit"]["q1"] == 600
    assert rows["profit"]["q2"] == 700
    assert rows["profit"]["total"] == 1300  # depends on computed profit.q1 + profit.q2


def test_matrix_overwrites_client_cell_value() -> None:
    fields = _financials_fields()
    data = {"financials": [
        {"_row_id": "rev",  "q1": 1000, "q2": 1200, "total": 999999},
        {"_row_id": "cost", "q1": 400,  "q2": 500},
        {"_row_id": "profit"},
    ]}
    out = apply_calculations(fields, data)
    rows = {r["_row_id"]: r for r in out["financials"]}
    assert rows["rev"]["total"] == 2200  # client lie overwritten


def test_matrix_no_cell_config_untouched() -> None:
    fields = [{"field": "t", "type": "json", "table_config": {
        "row_mode": "fixed",
        "columns": [{"id": "a", "type": "number"}],
        "rows": [{"id": "r1"}],
    }}]
    data = {"t": [{"_row_id": "r1", "a": 5}]}
    out = apply_calculations(fields, data)
    assert out["t"] == [{"_row_id": "r1", "a": 5}]
