"""Write-time application of calculated fields (store-on-write).

Operates on plain schema-field dicts (as stored in the schema JSON) so it has
no dependency on workflow models — importing it never creates a cycle.
"""

from __future__ import annotations

from typing import Any

from calc.evaluator import CalcContext, evaluate_node
from calc.spec import calc_field_refs


def _column_topo_order(columns: list[dict]) -> list[dict]:
    """Order computed columns so col-refs to other computed columns precede."""
    by_id = {c["id"]: c for c in columns}
    order: list[dict] = []
    done: set[str] = set()

    def col_refs(node: Any) -> set[str]:
        refs: set[str] = set()
        if isinstance(node, dict):
            if node.get("t") == "col":
                refs.add(str(node.get("col")))
            elif node.get("t") == "binary":
                refs |= col_refs(node.get("left"))
                refs |= col_refs(node.get("right"))
        return refs

    visiting: set[str] = set()

    def visit(col: dict) -> None:
        cid = col["id"]
        # `done` = already ordered; `visiting` = on the current DFS path, so a
        # re-entry is a back-edge (cycle). Skip both — config validation rejects
        # cycles; this only keeps eval order-stable and loop-free as a fallback.
        if cid in done or cid in visiting:
            return
        visiting.add(cid)
        for ref in sorted(col_refs(col.get("calc")) & set(by_id)):
            if ref != cid:
                visit(by_id[ref])
        visiting.discard(cid)
        done.add(cid)
        order.append(col)

    for col in columns:
        visit(col)
    return order


def apply_calculations(
    fields: list[dict], data: dict[str, Any], base: dict[str, Any] | None = None
) -> dict[str, Any]:
    result = dict(data)
    merged: dict[str, Any] = {**(base or {}), **result}

    # 1. Per-row computed columns.
    for f in fields:
        table_config = f.get("table_config")
        if not isinstance(table_config, dict):
            continue
        columns = [c for c in (table_config.get("columns") or []) if isinstance(c, dict)]
        computed = [c for c in columns if c.get("calc") is not None and c.get("id")]
        if not computed:
            continue
        rows = merged.get(f["field"])
        if not isinstance(rows, list):
            continue
        new_rows: list[Any] = []
        for row in rows:
            if not isinstance(row, dict):
                new_rows.append(row)
                continue
            new_row = dict(row)
            for col in _column_topo_order(computed):
                ctx = CalcContext(field_values=merged, table_rows={}, row=new_row)
                new_row[col["id"]] = evaluate_node(col["calc"], ctx)
            new_rows.append(new_row)
        result[f["field"]] = new_rows
        merged[f["field"]] = new_rows

    # 1b. Fixed-row matrix cell calcs (absolute cell references within one grid).
    from calc.spec import cell_topo_order

    for f in fields:
        table_config = f.get("table_config")
        if not isinstance(table_config, dict):
            continue
        if (table_config.get("row_mode") or "dynamic") != "fixed":
            continue
        preset_rows = [r for r in (table_config.get("rows") or []) if isinstance(r, dict)]
        calc_by_cell: dict[tuple[str, str], dict] = {}
        for r in preset_rows:
            cell_cfg = r.get("cell_config")
            if not isinstance(cell_cfg, dict):
                continue
            rid = str(r.get("id"))
            for col_id, cfg in cell_cfg.items():
                if isinstance(cfg, dict) and cfg.get("calc") is not None:
                    calc_by_cell[(rid, str(col_id))] = cfg["calc"]
        if not calc_by_cell:
            continue
        rows = merged.get(f["field"])
        if not isinstance(rows, list):
            continue
        cells_by_row: dict[str, dict] = {}
        for row in rows:
            if isinstance(row, dict):
                cells_by_row[str(row.get("_row_id"))] = dict(row)
        for rid, col_id in cell_topo_order(calc_by_cell):
            if rid not in cells_by_row:
                continue
            ctx = CalcContext(field_values=merged, table_rows={}, cells=cells_by_row)
            cells_by_row[rid][col_id] = evaluate_node(calc_by_cell[(rid, col_id)], ctx)
        new_rows = [
            cells_by_row.get(str(row.get("_row_id")), row) if isinstance(row, dict) else row
            for row in rows
        ]
        result[f["field"]] = new_rows
        merged[f["field"]] = new_rows

    # 2. Calc fields, in dependency order.
    calc_by_field = {f["field"]: f["calc"] for f in fields if f.get("calc") is not None}
    if not calc_by_field:
        return result

    # Local topo (duplicated tiny logic keeps apply dependency-light).
    calc_names = set(calc_by_field)
    deps = {n: (calc_field_refs(node) & calc_names) - {n} for n, node in calc_by_field.items()}
    order: list[str] = []
    done: set[str] = set()

    def visit(name: str, stack: set[str]) -> None:
        if name in done:
            return
        if name in stack:  # defensive: cycle → skip (config validation rejects these)
            return
        for dep in sorted(deps[name]):
            visit(dep, stack | {name})
        done.add(name)
        order.append(name)

    for name in sorted(calc_by_field):
        visit(name, set())

    table_rows = {
        f["field"]: merged[f["field"]]
        for f in fields
        if isinstance(merged.get(f["field"]), list)
    }
    for name in order:
        ctx = CalcContext(field_values=merged, table_rows=table_rows)
        value = evaluate_node(calc_by_field[name], ctx)
        result[name] = value
        merged[name] = value

    return result
