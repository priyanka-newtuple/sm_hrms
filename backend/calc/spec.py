"""Structural validation, reference checking, and dependency ordering for CalcNode.

Kept separate from the evaluator so it can be imported by schema-config
validation (workflow) without pulling evaluation logic. Dependency-free —
operates on plain dicts, so importing it never creates a cycle with `workflow`.
"""

from __future__ import annotations

from typing import Any

from calc.evaluator import AGG_FNS, BIN_OPS


class CalcCycleError(Exception):
    def __init__(self, fields: list[str]) -> None:
        self.fields = fields
        super().__init__(f"calculated fields form a cycle: {', '.join(sorted(fields))}")


def validate_calc_node(
    node: Any,
    *,
    field_names: set[str],
    table_columns: dict[str, set[str]],
    allow_col: bool,
    allow_cell: bool = False,
    allow_agg: bool = True,
    cell_coords: set[tuple[str, str]] | frozenset = frozenset(),
) -> list[str]:
    """Return a list of human-readable error strings; empty means valid.

    ``field_names`` = every field id in the schema.
    ``table_columns`` = { table_field_id: {column_id, ...} }.
    ``allow_col`` = True only when validating a per-row column calc.
    ``allow_cell`` = True only when validating a fixed-row cell calc.
    ``allow_agg`` = False inside a cell calc (whole-column sum is wrong for metric rows).
    ``cell_coords`` = valid (rowId, colId) pairs when ``allow_cell``.
    """
    errors: list[str] = []
    _walk(node, field_names, table_columns, allow_col, allow_cell, allow_agg, cell_coords, errors)
    return errors


def _walk(
    node: Any,
    field_names: set[str],
    table_columns: dict[str, set[str]],
    allow_col: bool,
    allow_cell: bool,
    allow_agg: bool,
    cell_coords: set[tuple[str, str]] | frozenset,
    errors: list[str],
) -> None:
    if not isinstance(node, dict):
        errors.append("calc node must be an object")
        return
    kind = node.get("t")
    if kind == "const":
        if not isinstance(node.get("value"), (int, float)) or isinstance(node.get("value"), bool):
            errors.append("const node requires a numeric 'value'")
    elif kind == "field":
        name = node.get("field")
        if name not in field_names:
            errors.append(f"calc references unknown field '{name}'")
    elif kind == "col":
        if not allow_col:
            errors.append("column reference is only allowed inside a column calculation")
        elif not isinstance(node.get("col"), str) or not node.get("col"):
            errors.append("col node requires a 'col' id")
    elif kind == "cell":
        if not allow_cell:
            errors.append("cell reference is only allowed inside a fixed-row cell calculation")
        else:
            coord = (str(node.get("row")), str(node.get("col")))
            if coord not in cell_coords:
                errors.append(f"cell reference ({coord[0]!r}, {coord[1]!r}) does not exist in this grid")
    elif kind == "agg":
        if not allow_agg:
            errors.append("aggregate is not allowed inside a cell calculation")
            return
        if node.get("fn") not in AGG_FNS:
            errors.append(f"aggregate fn must be one of {sorted(AGG_FNS)}")
        table = node.get("table")
        if table not in table_columns:
            errors.append(f"aggregate references unknown table field '{table}'")
        elif node.get("column") not in table_columns[table]:
            errors.append(f"aggregate references unknown column '{node.get('column')}' on table '{table}'")
    elif kind == "binary":
        if node.get("op") not in BIN_OPS:
            errors.append(f"binary op must be one of {sorted(BIN_OPS)}")
        _walk(node.get("left"), field_names, table_columns, allow_col, allow_cell, allow_agg, cell_coords, errors)
        _walk(node.get("right"), field_names, table_columns, allow_col, allow_cell, allow_agg, cell_coords, errors)
    else:
        errors.append(f"unknown calc node type '{kind}'")


def calc_field_refs(node: Any) -> set[str]:
    """Field + table names referenced anywhere in the tree (top-level scope)."""
    refs: set[str] = set()

    def visit(n: Any) -> None:
        if not isinstance(n, dict):
            return
        kind = n.get("t")
        if kind == "field":
            refs.add(str(n.get("field")))
        elif kind == "agg":
            refs.add(str(n.get("table")))
        elif kind == "binary":
            visit(n.get("left"))
            visit(n.get("right"))

    visit(node)
    return refs


def topo_order(calc_by_field: dict[str, dict]) -> list[str]:
    """Return calc field names ordered so dependencies precede dependents.

    Only edges between calc fields matter (references to plain user fields /
    tables are inputs, already present). Raises CalcCycleError on a cycle.
    """
    calc_names = set(calc_by_field)
    # Keep the self-edge (do NOT subtract {name}): a field referencing itself is a
    # 1-node cycle and must raise below, not be silently accepted.
    deps = {
        name: (calc_field_refs(node) & calc_names)
        for name, node in calc_by_field.items()
    }
    order: list[str] = []
    temp: set[str] = set()
    done: set[str] = set()

    def visit(name: str, stack: list[str]) -> None:
        if name in done:
            return
        if name in temp:
            raise CalcCycleError(stack + [name])
        temp.add(name)
        for dep in sorted(deps[name]):
            visit(dep, stack + [name])
        temp.discard(name)
        done.add(name)
        order.append(name)

    for name in sorted(calc_by_field):
        visit(name, [])
    return order


def cell_refs(node: Any) -> set[tuple[str, str]]:
    """Every (rowId, colId) referenced anywhere in a cell-calc tree."""
    refs: set[tuple[str, str]] = set()

    def visit(n: Any) -> None:
        if not isinstance(n, dict):
            return
        if n.get("t") == "cell":
            refs.add((str(n.get("row")), str(n.get("col"))))
        elif n.get("t") == "binary":
            visit(n.get("left"))
            visit(n.get("right"))

    visit(node)
    return refs


def cell_topo_order(calc_by_cell: dict[tuple[str, str], dict]) -> list[tuple[str, str]]:
    """Order computed cells so cell-refs to other computed cells precede.

    Only edges between computed cells matter (refs to input cells are leaves).
    Raises CalcCycleError on a cycle.
    """
    keys = set(calc_by_cell)
    # Keep the self-edge (do NOT subtract {k}): a cell referencing its own
    # coordinate is a 1-node cycle and must raise below, not be accepted.
    deps = {k: (cell_refs(node) & keys) for k, node in calc_by_cell.items()}
    order: list[tuple[str, str]] = []
    temp: set[tuple[str, str]] = set()
    done: set[tuple[str, str]] = set()

    def visit(key: tuple[str, str], stack: list[tuple[str, str]]) -> None:
        if key in done:
            return
        if key in temp:
            raise CalcCycleError([f"{r}:{c}" for r, c in stack + [key]])
        temp.add(key)
        for dep in sorted(deps[key]):
            visit(dep, stack + [key])
        temp.discard(key)
        done.add(key)
        order.append(key)

    for key in sorted(calc_by_cell):
        visit(key, [])
    return order


def column_refs(node: Any) -> set[str]:
    """Sibling-column ids referenced anywhere in a per-row column-calc tree."""
    refs: set[str] = set()

    def visit(n: Any) -> None:
        if not isinstance(n, dict):
            return
        if n.get("t") == "col":
            refs.add(str(n.get("col")))
        elif n.get("t") == "binary":
            visit(n.get("left"))
            visit(n.get("right"))

    visit(node)
    return refs


def column_topo_order(calc_by_col: dict[str, dict]) -> list[str]:
    """Order computed columns so col-refs to other computed columns precede.

    Only edges between computed columns matter. Raises CalcCycleError on a cycle.
    """
    keys = set(calc_by_col)
    # Keep the self-edge (do NOT subtract {k}): a column referencing itself is a
    # 1-node cycle and must raise below, not be accepted.
    deps = {k: (column_refs(node) & keys) for k, node in calc_by_col.items()}
    order: list[str] = []
    temp: set[str] = set()
    done: set[str] = set()

    def visit(key: str, stack: list[str]) -> None:
        if key in done:
            return
        if key in temp:
            raise CalcCycleError(stack + [key])
        temp.add(key)
        for dep in sorted(deps[key]):
            visit(dep, stack + [key])
        temp.discard(key)
        done.add(key)
        order.append(key)

    for key in sorted(calc_by_col):
        visit(key, [])
    return order
