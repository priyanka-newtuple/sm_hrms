import { useState, useEffect } from 'react';
import { Plus, X } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { evaluateNode } from '../../../../../shared/utils/calc';
import type { CalcNode } from '../../../../../shared/utils/calc';
import { SegmentedControl } from '@/core/components/SegmentedControl';
import { cn } from '@/lib/utils';

type RefKind = 'field' | 'col' | 'cell';
type BinOp = 'add' | 'sub' | 'mul' | 'div';
type AggFn = 'sum' | 'count' | 'avg' | 'min' | 'max';
type Operand =
  | { kind: 'const'; value: number }
  | { kind: 'ref'; id: string }
  | { kind: 'cell'; row: string; col: string };

const OPS: { value: BinOp; label: string }[] = [
  { value: 'add', label: '+' },
  { value: 'sub', label: '−' },
  { value: 'mul', label: '×' },
  { value: 'div', label: '÷' },
];

const AGG_FNS: { value: AggFn; label: string }[] = [
  { value: 'sum', label: 'SUM' },
  { value: 'count', label: 'COUNT' },
  { value: 'avg', label: 'AVG' },
  { value: 'min', label: 'MIN' },
  { value: 'max', label: 'MAX' },
];

// ponytail: this builder only round-trips the exact shapes it can produce
// (left-nested binary chain of leaf operands, or a bare/plus-wrapped agg).
// A calc hand-authored via JSON that doesn't match falls back to the default
// state below rather than crashing — upgrade to a generic AST editor if that
// becomes a real workflow. Cell mode reuses the arithmetic chain; its leaf
// operands are cells (row × col) or constants (field operands are a follow-up).

function leafNode(refKind: RefKind, operand: Operand): CalcNode {
  if (operand.kind === 'const') return { t: 'const', value: operand.value };
  if (operand.kind === 'cell') return { t: 'cell', row: operand.row, col: operand.col };
  return refKind === 'field' ? { t: 'field', field: operand.id } : { t: 'col', col: operand.id };
}

function leafOperand(refKind: RefKind, node: CalcNode): Operand | null {
  if (node.t === 'const') return { kind: 'const', value: node.value };
  if (refKind === 'cell' && node.t === 'cell') return { kind: 'cell', row: node.row, col: node.col };
  if (refKind === 'field' && node.t === 'field') return { kind: 'ref', id: node.field };
  if (refKind === 'col' && node.t === 'col') return { kind: 'ref', id: node.col };
  return null;
}

function flattenArithmetic(
  refKind: RefKind,
  node: CalcNode,
): { operands: Operand[]; ops: BinOp[] } | null {
  const leaf = leafOperand(refKind, node);
  if (leaf) return { operands: [leaf], ops: [] };
  if (node.t === 'binary') {
    const left = flattenArithmetic(refKind, node.left);
    const right = leafOperand(refKind, node.right);
    if (!left || !right) return null;
    return { operands: [...left.operands, right], ops: [...left.ops, node.op] };
  }
  return null;
}

function buildArithmetic(refKind: RefKind, operands: Operand[], ops: BinOp[]): CalcNode | undefined {
  if (operands.length === 0) return undefined;
  let node = leafNode(refKind, operands[0]);
  for (let i = 1; i < operands.length; i++) {
    node = { t: 'binary', op: ops[i - 1] ?? 'add', left: node, right: leafNode(refKind, operands[i]) };
  }
  return node;
}

function flattenAggregate(
  node: CalcNode,
): { fn: AggFn; table: string; column: string; plusField?: string } | null {
  if (node.t === 'agg') return { fn: node.fn, table: node.table, column: node.column };
  if (node.t === 'binary' && node.op === 'add' && node.left.t === 'agg' && node.right.t === 'field') {
    return { fn: node.left.fn, table: node.left.table, column: node.left.column, plusField: node.right.field };
  }
  return null;
}

interface State {
  enabled: boolean;
  calcMode: 'arithmetic' | 'aggregate';
  arithOperands: Operand[];
  arithOps: BinOp[];
  aggFn: AggFn;
  aggTable: string;
  aggColumn: string;
  aggPlus: boolean;
  aggPlusField: string;
}

function initState(
  mode: 'field' | 'column' | 'cell',
  refKind: RefKind,
  value: CalcNode | undefined,
  cellRows?: { id: string; label: string }[],
  cellColumns?: { id: string; label: string }[],
  embedded?: boolean,
): State {
  const enabled = embedded ? true : !!value;
  if (mode === 'field' && value) {
    const agg = flattenAggregate(value);
    if (agg) {
      return {
        enabled,
        calcMode: 'aggregate',
        arithOperands: [],
        arithOps: [],
        aggFn: agg.fn,
        aggTable: agg.table,
        aggColumn: agg.column,
        aggPlus: !!agg.plusField,
        aggPlusField: agg.plusField ?? '',
      };
    }
  }
  const arith = value ? flattenArithmetic(refKind, value) : null;
  const defaultOperand = (): Operand =>
    mode === 'cell' && cellRows?.[0] && cellColumns?.[0]
      ? { kind: 'cell', row: cellRows[0].id, col: cellColumns[0].id }
      : { kind: 'const', value: 0 };
  return {
    enabled,
    calcMode: 'arithmetic',
    arithOperands: arith?.operands ?? [defaultOperand(), defaultOperand()],
    arithOps: arith?.ops ?? ['add'],
    aggFn: 'sum',
    aggTable: '',
    aggColumn: '',
    aggPlus: false,
    aggPlusField: '',
  };
}

// Node emission is separate from `enabled`/mode bookkeeping: an aggregate
// mid-configuration (table chosen, column not yet) has no valid CalcNode yet,
// but the builder must stay open — visibility is driven by `state.enabled`,
// never by whether this happens to return something.
function computeNode(mode: 'field' | 'column' | 'cell', refKind: RefKind, s: State): CalcNode | undefined {
  if (!s.enabled) return undefined;
  if (mode === 'field' && s.calcMode === 'aggregate') {
    if (!s.aggTable || !s.aggColumn) return undefined;
    const agg: CalcNode = { t: 'agg', fn: s.aggFn, table: s.aggTable, column: s.aggColumn };
    if (s.aggPlus && s.aggPlusField) {
      return { t: 'binary', op: 'add', left: agg, right: { t: 'field', field: s.aggPlusField } };
    }
    return agg;
  }
  return buildArithmetic(refKind, s.arithOperands, s.arithOps);
}

function sampleCtx(
  mode: 'field' | 'column' | 'cell',
  numericFields: { id: string; label: string }[],
  tableFields: { id: string; label: string; columns: { id: string; label: string }[] }[],
  siblingColumns?: { id: string; label: string }[],
  cellRows?: { id: string; label: string }[],
  cellColumns?: { id: string; label: string }[],
) {
  if (mode === 'cell') {
    const cells: Record<string, Record<string, unknown>> = {};
    (cellRows ?? []).forEach((r) => {
      cells[r.id] = {};
      (cellColumns ?? []).forEach((c) => { cells[r.id][c.id] = 2; });
    });
    return { fieldValues: {}, tableRows: {}, cells };
  }
  if (mode === 'column') {
    const row: Record<string, unknown> = {};
    (siblingColumns ?? []).forEach((c) => { row[c.id] = 2; });
    return { fieldValues: {}, tableRows: {}, row };
  }
  const fieldValues: Record<string, unknown> = {};
  numericFields.forEach((f) => { fieldValues[f.id] = 2; });
  const tableRows: Record<string, unknown> = {};
  tableFields.forEach((t) => {
    tableRows[t.id] = [
      Object.fromEntries(t.columns.map((c) => [c.id, 2])),
      Object.fromEntries(t.columns.map((c) => [c.id, 3])),
    ];
  });
  return { fieldValues, tableRows };
}

interface OperandPickerProps {
  operand: Operand;
  options: { id: string; label: string }[];
  refKind: RefKind;
  cellRows?: { id: string; label: string }[];
  cellColumns?: { id: string; label: string }[];
  onChange: (o: Operand) => void;
}

function OperandPicker({ operand, options, refKind, cellRows, cellColumns, onChange }: OperandPickerProps) {
  if (refKind === 'cell') {
    const cellOp = operand.kind === 'cell' ? operand : null;
    return (
      <div className="flex min-w-0 flex-1 items-center gap-1">
        <select
          value={operand.kind === 'cell' ? operand.row : '__const__'}
          onChange={(e) =>
            e.target.value === '__const__'
              ? onChange({ kind: 'const', value: 0 })
              : onChange({ kind: 'cell', row: e.target.value, col: cellOp?.col ?? cellColumns?.[0]?.id ?? '' })
          }
          className="min-w-0 flex-1 px-2 py-1.5 border border-border rounded-lg text-sm outline-none focus:ring-2 focus:ring-cobalt focus:border-cobalt"
        >
          <option value="__const__">Number…</option>
          {(cellRows ?? []).map((r) => (
            <option key={r.id} value={r.id}>{r.label}</option>
          ))}
        </select>
        {operand.kind === 'cell' && (
          <select
            value={operand.col}
            onChange={(e) => onChange({ kind: 'cell', row: operand.row, col: e.target.value })}
            className="min-w-0 flex-1 px-2 py-1.5 border border-border rounded-lg text-sm outline-none focus:ring-2 focus:ring-cobalt focus:border-cobalt"
          >
            {(cellColumns ?? []).map((c) => (
              <option key={c.id} value={c.id}>{c.label}</option>
            ))}
          </select>
        )}
        {operand.kind === 'const' && (
          <input
            type="number"
            value={operand.value}
            onChange={(e) => onChange({ kind: 'const', value: Number(e.target.value || 0) })}
            className="w-20 shrink-0 px-2 py-1.5 border border-border rounded-lg text-sm outline-none focus:ring-2 focus:ring-cobalt focus:border-cobalt"
          />
        )}
      </div>
    );
  }
  const shrink = refKind === 'col';
  return (
    <div className={cn('flex items-center gap-1', shrink && 'min-w-0 flex-1')}>
      <select
        value={operand.kind === 'ref' ? operand.id : '__const__'}
        onChange={(e) =>
          onChange(e.target.value === '__const__' ? { kind: 'const', value: 0 } : { kind: 'ref', id: e.target.value })
        }
        className={cn('px-2 py-1.5 border border-border rounded-lg text-sm outline-none focus:ring-2 focus:ring-cobalt focus:border-cobalt', shrink && 'min-w-0 flex-1')}
      >
        <option value="__const__">Number…</option>
        {options.map((o) => (
          <option key={o.id} value={o.id}>{o.label}</option>
        ))}
      </select>
      {operand.kind === 'const' && (
        <input
          type="number"
          value={operand.value}
          onChange={(e) => onChange({ kind: 'const', value: Number(e.target.value || 0) })}
          className={cn('w-20 px-2 py-1.5 border border-border rounded-lg text-sm outline-none focus:ring-2 focus:ring-cobalt focus:border-cobalt', shrink && 'shrink-0')}
        />
      )}
    </div>
  );
}

export interface CalcBuilderProps {
  value?: CalcNode;
  onChange: (c: CalcNode | undefined) => void;
  numericFields: { id: string; label: string }[];
  tableFields: { id: string; label: string; columns: { id: string; label: string }[] }[];
  mode: 'field' | 'column' | 'cell';
  siblingColumns?: { id: string; label: string }[];
  cellRows?: { id: string; label: string }[];
  cellColumns?: { id: string; label: string }[];
  embedded?: boolean;
}

export default function CalcBuilder({
  value,
  onChange,
  numericFields,
  tableFields,
  mode,
  siblingColumns,
  cellRows,
  cellColumns,
  embedded,
}: CalcBuilderProps) {
  const refKind: RefKind = mode === 'column' ? 'col' : mode === 'cell' ? 'cell' : 'field';
  const refOptions = mode === 'column' ? siblingColumns ?? [] : numericFields;
  const [state, setLocalState] = useState<State>(() => initState(mode, refKind, value, cellRows, cellColumns, embedded));

  const setState = (patch: Partial<State>) => {
    const next = { ...state, ...patch };
    setLocalState(next);
    onChange(computeNode(mode, refKind, next));
  };

  // Embedded (inside CellConfigPopover): the popover's mode radio is the on/off,
  // so there is no internal switch — emit the (default) formula once on mount.
  useEffect(() => {
    if (embedded) onChange(computeNode(mode, refKind, state));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const previewNode = state.enabled ? computeNode(mode, refKind, state) : undefined;
  const preview = previewNode
    ? evaluateNode(previewNode, sampleCtx(mode, numericFields, tableFields, siblingColumns, cellRows, cellColumns))
    : null;

  const selectedTable = tableFields.find((t) => t.id === state.aggTable);

  return (
    <div className={embedded ? 'space-y-3' : 'space-y-3 rounded-xl border border-border bg-card p-3'}>
      {!embedded && (
        <div className="flex items-center justify-between">
          <div>
            <span className="text-sm font-medium text-foreground">
              {mode === 'column' ? 'Calculated column' : 'Calculated'}
            </span>
            <p className="text-xs text-muted-foreground mt-0.5">
              Value is computed automatically and read-only.
            </p>
          </div>
          <Switch checked={state.enabled} onCheckedChange={(checked) => setState({ enabled: checked })} />
        </div>
      )}

      {(embedded || state.enabled) && (
        <div className="space-y-3">
          {mode === 'field' && (
            <select
              value={state.calcMode}
              onChange={(e) => setState({ calcMode: e.target.value as State['calcMode'] })}
              className="w-full px-3 py-2 border border-border rounded-lg text-sm"
            >
              <option value="arithmetic">Arithmetic</option>
              <option value="aggregate">Aggregate</option>
            </select>
          )}

          {(mode === 'column' || mode === 'cell' || state.calcMode === 'arithmetic') && (
            <div className={cn('flex gap-2', refKind === 'field' ? 'flex-wrap items-center' : 'flex-col')}>
              {state.arithOperands.map((operand, i) => (
                <div key={i} className={cn('flex items-center gap-2', refKind !== 'field' && 'w-full min-w-0')}>
                  {i > 0 && (
                    <SegmentedControl
                      size="sm"
                      options={OPS}
                      value={state.arithOps[i - 1] ?? 'add'}
                      onChange={(op) => {
                        const ops = [...state.arithOps];
                        ops[i - 1] = op;
                        setState({ arithOps: ops });
                      }}
                    />
                  )}
                  <OperandPicker
                    operand={operand}
                    options={refOptions}
                    refKind={refKind}
                    cellRows={cellRows}
                    cellColumns={cellColumns}
                    onChange={(o) => {
                      const operands = [...state.arithOperands];
                      operands[i] = o;
                      setState({ arithOperands: operands });
                    }}
                  />
                  {i >= 2 && (
                    <button
                      type="button"
                      onClick={() => {
                        setState({
                          arithOperands: state.arithOperands.filter((_, idx) => idx !== i),
                          arithOps: state.arithOps.filter((_, idx) => idx !== i - 1),
                        });
                      }}
                      className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-destructive"
                      title="Remove operand"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              ))}
              <button
                type="button"
                onClick={() =>
                  setState({
                    arithOperands: [...state.arithOperands, { kind: 'const', value: 0 }],
                    arithOps: [...state.arithOps, 'add'],
                  })
                }
                className="flex items-center gap-1 rounded-lg border border-dashed border-border px-2 py-1.5 text-xs text-muted-foreground hover:bg-muted/50"
              >
                <Plus className="h-3 w-3" /> Add operand
              </button>
            </div>
          )}

          {mode === 'field' && state.calcMode === 'aggregate' && (
            <div className="space-y-2">
              <div className="grid grid-cols-3 gap-2">
                <select
                  value={state.aggFn}
                  onChange={(e) => setState({ aggFn: e.target.value as AggFn })}
                  className="px-2 py-1.5 border border-border rounded-lg text-sm outline-none focus:ring-2 focus:ring-cobalt focus:border-cobalt"
                >
                  {AGG_FNS.map((f) => (
                    <option key={f.value} value={f.value}>{f.label}</option>
                  ))}
                </select>
                <select
                  value={state.aggTable}
                  onChange={(e) => setState({ aggTable: e.target.value, aggColumn: '' })}
                  className="px-2 py-1.5 border border-border rounded-lg text-sm outline-none focus:ring-2 focus:ring-cobalt focus:border-cobalt"
                >
                  <option value="">Table field…</option>
                  {tableFields.map((t) => (
                    <option key={t.id} value={t.id}>{t.label}</option>
                  ))}
                </select>
                <select
                  value={state.aggColumn}
                  onChange={(e) => setState({ aggColumn: e.target.value })}
                  disabled={!selectedTable}
                  className="px-2 py-1.5 border border-border rounded-lg text-sm outline-none focus:ring-2 focus:ring-cobalt focus:border-cobalt disabled:bg-muted"
                >
                  <option value="">Column…</option>
                  {(selectedTable?.columns ?? []).map((c) => (
                    <option key={c.id} value={c.id}>{c.label}</option>
                  ))}
                </select>
              </div>
              <label className="flex items-center gap-2 text-sm text-foreground">
                <input
                  type="checkbox"
                  checked={state.aggPlus}
                  onChange={(e) => setState({ aggPlus: e.target.checked })}
                />
                + another field
              </label>
              {state.aggPlus && (
                <select
                  value={state.aggPlusField}
                  onChange={(e) => setState({ aggPlusField: e.target.value })}
                  className="w-full px-2 py-1.5 border border-border rounded-lg text-sm outline-none focus:ring-2 focus:ring-cobalt focus:border-cobalt"
                >
                  <option value="">Field…</option>
                  {numericFields.map((f) => (
                    <option key={f.id} value={f.id}>{f.label}</option>
                  ))}
                </select>
              )}
            </div>
          )}

          <div className="flex items-center gap-2 pt-0.5 text-xs font-medium text-muted-foreground">
            Result
            <Badge variant="default" className="font-mono tabular-nums">
              = {preview === null ? '—' : preview}
            </Badge>
          </div>
        </div>
      )}
    </div>
  );
}
