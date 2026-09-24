"""Pure evaluator for the shared CalcNode expression tree.

Every node resolves to ``float | None``. ``None`` on non-numeric input or
divide-by-zero; never raises. A missing operand of a binary arithmetic op
(+ - * /) is treated as 0, not null — so `2 + <blank> = 2`. Aggregates are
unaffected: they skip empty cells and stay null only when every cell is
empty. Mirrors frontend `calc.ts` exactly; both are pinned by
`calc_golden.json`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

AGG_FNS = frozenset({"sum", "count", "avg", "min", "max"})
BIN_OPS = frozenset({"add", "sub", "mul", "div"})


@dataclass(frozen=True)
class CalcContext:
    field_values: dict[str, Any]
    table_rows: dict[str, Any]
    row: dict[str, Any] | None = None  # set only when evaluating a per-row column calc
    cells: dict[str, Any] | None = None  # rowId -> {colId: value}; set for fixed-row cell calcs


def is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, tuple)):
        return len(value) == 0
    return False


def to_number(value: Any) -> float | None:
    # bool is a subclass of int — treat booleans as non-numeric.
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "":
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def evaluate_node(node: Any, ctx: CalcContext) -> float | None:
    if not isinstance(node, dict):
        return None
    kind = node.get("t")
    if kind == "const":
        return to_number(node.get("value"))
    if kind == "field":
        return to_number(ctx.field_values.get(node.get("field")))
    if kind == "col":
        if ctx.row is None:
            return None
        return to_number(ctx.row.get(node.get("col")))
    if kind == "cell":
        if ctx.cells is None:
            return None
        row = ctx.cells.get(node.get("row"))
        if not isinstance(row, dict):
            return None
        return to_number(row.get(node.get("col")))
    if kind == "agg":
        return _evaluate_agg(node, ctx)
    if kind == "binary":
        return _evaluate_binary(node, ctx)
    return None


def _evaluate_agg(node: dict, ctx: CalcContext) -> float | None:
    fn = node.get("fn")
    rows = ctx.table_rows.get(node.get("table"))
    if not isinstance(rows, list):
        rows = []
    column = node.get("column")
    cells = [row.get(column) for row in rows if isinstance(row, dict)]
    if fn == "count":
        return float(sum(1 for cell in cells if not is_empty(cell)))
    numbers = [n for n in (to_number(cell) for cell in cells) if n is not None]
    if not numbers:
        return None
    if fn == "sum":
        return float(sum(numbers))
    if fn == "avg":
        return sum(numbers) / len(numbers)
    if fn == "min":
        return min(numbers)
    if fn == "max":
        return max(numbers)
    return None


def _evaluate_binary(node: dict, ctx: CalcContext) -> float | None:
    left = evaluate_node(node.get("left"), ctx)
    right = evaluate_node(node.get("right"), ctx)
    # A missing operand acts as 0 for arithmetic (2 + blank = 2), not null.
    left = 0.0 if left is None else left
    right = 0.0 if right is None else right
    op = node.get("op")
    if op == "add":
        return left + right
    if op == "sub":
        return left - right
    if op == "mul":
        return left * right
    if op == "div":
        return None if right == 0 else left / right
    return None
