// Shared calculated-fields evaluator. Mirrors backend/calc/evaluator.py exactly;
// both are pinned by backend/calc/calc_golden.json.
//
// A missing operand of a binary arithmetic op (+ - * /) is treated as 0, not
// null — so `2 + <blank> = 2`. Aggregates are unaffected: they skip empty
// cells and stay null only when every cell is empty.

export type CalcNode =
  | { t: 'const'; value: number }
  | { t: 'field'; field: string }
  | { t: 'col'; col: string }
  | { t: 'cell'; row: string; col: string }
  | { t: 'agg'; fn: 'sum' | 'count' | 'avg' | 'min' | 'max'; table: string; column: string }
  | { t: 'binary'; op: 'add' | 'sub' | 'mul' | 'div'; left: CalcNode; right: CalcNode };

export interface CalcContext {
  fieldValues: Record<string, unknown>;
  tableRows: Record<string, unknown>;
  row?: Record<string, unknown> | null;
  cells?: Record<string, Record<string, unknown>> | null;
}

export function isEmpty(value: unknown): boolean {
  if (value === null || value === undefined) return true;
  if (typeof value === 'string') return value.trim() === '';
  if (Array.isArray(value)) return value.length === 0;
  return false;
}

export function toNumber(value: unknown): number | null {
  if (value === null || value === undefined || typeof value === 'boolean') return null;
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (trimmed === '') return null;
    const n = Number(trimmed);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

export function evaluateNode(node: CalcNode | null | undefined, ctx: CalcContext): number | null {
  if (!node || typeof node !== 'object') return null;
  switch (node.t) {
    case 'const':
      return toNumber(node.value);
    case 'field':
      return toNumber(ctx.fieldValues[node.field]);
    case 'col':
      return ctx.row ? toNumber(ctx.row[node.col]) : null;
    case 'cell': {
      const r = ctx.cells?.[node.row];
      return r ? toNumber(r[node.col]) : null;
    }
    case 'agg':
      return evaluateAgg(node, ctx);
    case 'binary':
      return evaluateBinary(node, ctx);
    default:
      return null;
  }
}

function evaluateAgg(node: Extract<CalcNode, { t: 'agg' }>, ctx: CalcContext): number | null {
  const raw = ctx.tableRows[node.table];
  const rows = Array.isArray(raw) ? (raw as unknown[]) : [];
  const cells = rows
    .filter((r): r is Record<string, unknown> => !!r && typeof r === 'object')
    .map((r) => r[node.column]);
  if (node.fn === 'count') return cells.filter((c) => !isEmpty(c)).length;
  const nums = cells.map(toNumber).filter((n): n is number => n !== null);
  if (nums.length === 0) return null;
  switch (node.fn) {
    case 'sum':
      return nums.reduce((a, b) => a + b, 0);
    case 'avg':
      return nums.reduce((a, b) => a + b, 0) / nums.length;
    case 'min':
      return Math.min(...nums);
    case 'max':
      return Math.max(...nums);
    default:
      return null;
  }
}

function evaluateBinary(node: Extract<CalcNode, { t: 'binary' }>, ctx: CalcContext): number | null {
  const rawLeft = evaluateNode(node.left, ctx);
  const rawRight = evaluateNode(node.right, ctx);
  // A missing operand acts as 0 for arithmetic (2 + blank = 2), not null.
  const left = rawLeft === null ? 0 : rawLeft;
  const right = rawRight === null ? 0 : rawRight;
  switch (node.op) {
    case 'add':
      return left + right;
    case 'sub':
      return left - right;
    case 'mul':
      return left * right;
    case 'div':
      return right === 0 ? null : left / right;
    default:
      return null;
  }
}

import type { FormField, TableColumn, TableColumnType } from '../../core/types';

function colRefs(node: CalcNode | undefined): Set<string> {
  const refs = new Set<string>();
  const visit = (n: CalcNode | undefined) => {
    if (!n) return;
    if (n.t === 'col') refs.add(n.col);
    else if (n.t === 'binary') { visit(n.left); visit(n.right); }
  };
  visit(node);
  return refs;
}

function fieldRefs(node: CalcNode | undefined): Set<string> {
  const refs = new Set<string>();
  const visit = (n: CalcNode | undefined) => {
    if (!n) return;
    if (n.t === 'field') refs.add(n.field);
    else if (n.t === 'agg') refs.add(n.table);
    else if (n.t === 'binary') { visit(n.left); visit(n.right); }
  };
  visit(node);
  return refs;
}

function cellRefs(node: CalcNode | undefined): Set<string> {
  const refs = new Set<string>();
  const visit = (n: CalcNode | undefined) => {
    if (!n) return;
    if (n.t === 'cell') refs.add(`${n.row}${n.col}`);
    else if (n.t === 'binary') { visit(n.left); visit(n.right); }
  };
  visit(node);
  return refs;
}

function topo<T>(items: T[], id: (t: T) => string, deps: (t: T) => Set<string>): T[] {
  const byId = new Map(items.map((it) => [id(it), it]));
  const order: T[] = [];
  const done = new Set<string>();
  const stack = new Set<string>();
  const visit = (it: T) => {
    const key = id(it);
    if (done.has(key) || stack.has(key)) return; // cycle → skip (config validation rejects)
    stack.add(key);
    for (const d of deps(it)) if (byId.has(d) && d !== key) visit(byId.get(d)!);
    stack.delete(key);
    done.add(key);
    order.push(it);
  };
  items.forEach(visit);
  return order;
}

/** Return a copy of `values` with computed columns rewritten and calc fields filled. */
export function applyCalculations(
  fields: FormField[],
  values: Record<string, unknown>,
): Record<string, unknown> {
  const result: Record<string, unknown> = { ...values };

  // 1. Per-row computed columns.
  for (const f of fields) {
    const columns = (f.table_config?.columns ?? []) as TableColumn[];
    const computed = columns.filter((c) => c.calc);
    if (computed.length === 0) continue;
    const rows = result[f.id];
    if (!Array.isArray(rows)) continue;
    const ordered = topo(computed, (c) => c.id, (c) => colRefs(c.calc));
    result[f.id] = rows.map((row) => {
      if (!row || typeof row !== 'object') return row;
      const next: Record<string, unknown> = { ...(row as Record<string, unknown>) };
      for (const col of ordered) {
        next[col.id] = evaluateNode(col.calc!, { fieldValues: result, tableRows: {}, row: next });
      }
      return next;
    });
  }

  // 1b. Fixed-row matrix cell calcs (absolute cell references within one grid).
  for (const f of fields) {
    const cfg = f.table_config;
    if (!cfg || (cfg.row_mode ?? 'dynamic') !== 'fixed') continue;
    const calcCells: { key: string; row: string; col: string; calc: CalcNode }[] = [];
    for (const r of cfg.rows ?? []) {
      if (!r.cell_config) continue;
      for (const [colId, cellCfg] of Object.entries(r.cell_config)) {
        if (cellCfg?.calc) calcCells.push({ key: `${r.id}${colId}`, row: r.id, col: colId, calc: cellCfg.calc });
      }
    }
    if (calcCells.length === 0) continue;
    const rows = result[f.id];
    if (!Array.isArray(rows)) continue;
    const cellsByRow: Record<string, Record<string, unknown>> = {};
    for (const row of rows) {
      if (row && typeof row === 'object') {
        cellsByRow[String((row as Record<string, unknown>)._row_id)] = { ...(row as Record<string, unknown>) };
      }
    }
    const ordered = topo(calcCells, (c) => c.key, (c) => cellRefs(c.calc));
    for (const c of ordered) {
      const target = cellsByRow[c.row];
      if (target) target[c.col] = evaluateNode(c.calc, { fieldValues: result, tableRows: {}, cells: cellsByRow });
    }
    result[f.id] = rows.map((row) =>
      row && typeof row === 'object'
        ? cellsByRow[String((row as Record<string, unknown>)._row_id)] ?? row
        : row,
    );
  }

  // 2. Calc fields in dependency order.
  const calcFields = fields.filter((f) => f.calc);
  if (calcFields.length === 0) return result;
  const tableRows: Record<string, unknown> = {};
  for (const f of fields) if (Array.isArray(result[f.id])) tableRows[f.id] = result[f.id];
  const ordered = topo(calcFields, (f) => f.id, (f) => fieldRefs(f.calc));
  for (const f of ordered) {
    result[f.id] = evaluateNode(f.calc!, { fieldValues: result, tableRows });
  }
  return result;
}

// --- Fixed-row cell-config resolvers (shared by both FieldInput copies + entityForm) ---

/** The cell_config map for the fixed preset row that matches `row` (by _row_id). */
export function cellConfigFor(
  field: FormField,
  row: Record<string, unknown>,
): Record<string, { type?: TableColumnType; calc?: CalcNode; readonly?: boolean }> | undefined {
  if (field.table_config?.row_mode !== 'fixed') return undefined;
  const rowId = String(row._row_id ?? '');
  return field.table_config.rows?.find((r) => r.id === rowId)?.cell_config;
}

export function resolveCellType(
  field: FormField,
  row: Record<string, unknown>,
  column: TableColumn,
): TableColumnType {
  return cellConfigFor(field, row)?.[column.id]?.type ?? column.type;
}

export function isCellComputedOrReadonly(
  field: FormField,
  row: Record<string, unknown>,
  column: TableColumn,
): boolean {
  const cc = cellConfigFor(field, row)?.[column.id];
  return Boolean(cc?.calc || cc?.readonly);
}
