from __future__ import annotations

import pytest

from calc import spec
from calc.spec import CalcCycleError, cell_refs, cell_topo_order, column_topo_order


# --- Base spec validation (pure; no DB / EntityField) ---

def test_validate_ok_arithmetic() -> None:
    node = {"t": "binary", "op": "add",
            "left": {"t": "field", "field": "a"},
            "right": {"t": "field", "field": "b"}}
    errors = spec.validate_calc_node(node, field_names={"a", "b"}, table_columns={}, allow_col=False)
    assert errors == []


def test_validate_unknown_field_ref() -> None:
    node = {"t": "field", "field": "missing"}
    errors = spec.validate_calc_node(node, field_names={"a"}, table_columns={}, allow_col=False)
    assert any("missing" in e for e in errors)


def test_validate_agg_unknown_column() -> None:
    node = {"t": "agg", "fn": "sum", "table": "items", "column": "nope"}
    errors = spec.validate_calc_node(
        node, field_names={"items"}, table_columns={"items": {"amount"}}, allow_col=False
    )
    assert any("nope" in e for e in errors)


def test_validate_col_not_allowed_outside_column_calc() -> None:
    node = {"t": "col", "col": "qty"}
    errors = spec.validate_calc_node(node, field_names=set(), table_columns={}, allow_col=False)
    assert errors  # col ref illegal at field scope


def test_topo_order_chains() -> None:
    calc_by_field = {
        "net": {"t": "binary", "op": "sub", "left": {"t": "field", "field": "gross"}, "right": {"t": "field", "field": "tax"}},
        "gross": {"t": "binary", "op": "add", "left": {"t": "field", "field": "base"}, "right": {"t": "field", "field": "bonus"}},
    }
    order = spec.topo_order(calc_by_field)
    assert order.index("gross") < order.index("net")


def test_topo_order_cycle_raises() -> None:
    calc_by_field = {
        "a": {"t": "field", "field": "b"},
        "b": {"t": "field", "field": "a"},
    }
    with pytest.raises(CalcCycleError):
        spec.topo_order(calc_by_field)


# --- Cell validation (new) ---

def test_cell_ref_disallowed_by_default() -> None:
    node = {"t": "cell", "row": "r1", "col": "c1"}
    errors = spec.validate_calc_node(node, field_names=set(), table_columns={}, allow_col=False)
    assert errors  # cell not allowed at field/column scope


def test_cell_ref_ok_when_allowed_and_exists() -> None:
    node = {"t": "cell", "row": "r1", "col": "c1"}
    errors = spec.validate_calc_node(
        node, field_names=set(), table_columns={}, allow_col=False,
        allow_cell=True, allow_agg=False, cell_coords={("r1", "c1")},
    )
    assert errors == []


def test_cell_ref_unknown_coord_rejected() -> None:
    node = {"t": "cell", "row": "r1", "col": "nope"}
    errors = spec.validate_calc_node(
        node, field_names=set(), table_columns={}, allow_col=False,
        allow_cell=True, allow_agg=False, cell_coords={("r1", "c1")},
    )
    assert any("nope" in e for e in errors)


def test_agg_rejected_inside_cell_calc() -> None:
    node = {"t": "agg", "fn": "sum", "table": "t", "column": "c"}
    errors = spec.validate_calc_node(
        node, field_names={"t"}, table_columns={"t": {"c"}}, allow_col=False,
        allow_cell=True, allow_agg=False, cell_coords=set(),
    )
    assert any("aggregate" in e.lower() for e in errors)


def test_cell_refs_extracts_coords() -> None:
    node = {"t": "binary", "op": "sub",
            "left": {"t": "cell", "row": "rev", "col": "q1"},
            "right": {"t": "cell", "row": "cost", "col": "q1"}}
    assert cell_refs(node) == {("rev", "q1"), ("cost", "q1")}


def test_cell_topo_orders_dependencies() -> None:
    calc_by_cell = {
        ("profit", "total"): {"t": "binary", "op": "add",
            "left": {"t": "cell", "row": "profit", "col": "q1"},
            "right": {"t": "cell", "row": "profit", "col": "q2"}},
        ("profit", "q1"): {"t": "cell", "row": "rev", "col": "q1"},
        ("profit", "q2"): {"t": "cell", "row": "rev", "col": "q2"},
    }
    order = cell_topo_order(calc_by_cell)
    assert order.index(("profit", "q1")) < order.index(("profit", "total"))
    assert order.index(("profit", "q2")) < order.index(("profit", "total"))


def test_cell_topo_cycle_raises() -> None:
    calc_by_cell = {
        ("a", "x"): {"t": "cell", "row": "a", "col": "y"},
        ("a", "y"): {"t": "cell", "row": "a", "col": "x"},
    }
    with pytest.raises(CalcCycleError):
        cell_topo_order(calc_by_cell)


def test_column_topo_orders_dependencies() -> None:
    calc_by_col = {
        "total": {"t": "binary", "op": "add",
                  "left": {"t": "col", "col": "a"}, "right": {"t": "col", "col": "b"}},
        "a": {"t": "const", "value": 1},
        "b": {"t": "const", "value": 2},
    }
    order = column_topo_order(calc_by_col)
    assert order.index("a") < order.index("total")
    assert order.index("b") < order.index("total")


def test_column_topo_cycle_raises() -> None:
    calc_by_col = {"a": {"t": "col", "col": "b"}, "b": {"t": "col", "col": "a"}}
    with pytest.raises(CalcCycleError):
        column_topo_order(calc_by_col)


def test_cell_topo_self_reference_raises() -> None:
    calc_by_cell = {
        ("r1", "x"): {"t": "binary", "op": "add",
                      "left": {"t": "cell", "row": "r1", "col": "x"},
                      "right": {"t": "cell", "row": "r1", "col": "y"}},
    }
    with pytest.raises(CalcCycleError):
        cell_topo_order(calc_by_cell)


def test_column_topo_self_reference_raises() -> None:
    calc_by_col = {
        "a": {"t": "binary", "op": "add",
              "left": {"t": "col", "col": "a"}, "right": {"t": "col", "col": "b"}},
    }
    with pytest.raises(CalcCycleError):
        column_topo_order(calc_by_col)


def test_field_topo_self_reference_raises() -> None:
    calc_by_field = {
        "a": {"t": "binary", "op": "add",
              "left": {"t": "field", "field": "a"}, "right": {"t": "const", "value": 1}},
    }
    with pytest.raises(CalcCycleError):
        spec.topo_order(calc_by_field)
