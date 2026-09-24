// Run with: npx tsx src/shared/utils/calc.selfcheck.ts   (from frontend/)
// Loads the SAME golden fixture the backend uses and asserts parity.

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import assert from 'node:assert/strict';
import { evaluateNode, type CalcContext, type CalcNode } from './calc';

const here = dirname(fileURLToPath(import.meta.url));
const goldenPath = resolve(here, '../../../../backend/calc/calc_golden.json');
const golden = JSON.parse(readFileSync(goldenPath, 'utf8')) as Array<{
  name: string;
  spec: CalcNode;
  ctx: {
    field_values?: Record<string, unknown>;
    table_rows?: Record<string, unknown>;
    row?: Record<string, unknown>;
    cells?: Record<string, Record<string, unknown>>;
  };
  expected: number | null;
}>;

let passed = 0;
for (const c of golden) {
  const ctx: CalcContext = {
    fieldValues: c.ctx.field_values ?? {},
    tableRows: c.ctx.table_rows ?? {},
    row: c.ctx.row ?? null,
    cells: c.ctx.cells ?? null,
  };
  const result = evaluateNode(c.spec, ctx);
  if (c.expected === null) {
    assert.equal(result, null, `case ${c.name}: expected null, got ${result}`);
  } else {
    assert.ok(
      result !== null && Math.abs(result - c.expected) < 1e-9,
      `case ${c.name}: expected ${c.expected}, got ${result}`,
    );
  }
  passed += 1;
}
console.log(`calc parity: ${passed}/${golden.length} cases passed`);

import { applyCalculations } from './calc';
import type { FormField } from '../../core/types';

const numField = (id: string, calc?: FormField['calc']): FormField => ({
  id, label: id, type: 'number', required: false, system: false, ...(calc ? { calc } : {}),
});

// scalar arithmetic overwrites client value
{
  const fields: FormField[] = [
    numField('a'), numField('b'),
    numField('total', { t: 'binary', op: 'add', left: { t: 'field', field: 'a' }, right: { t: 'field', field: 'b' } }),
  ];
  const out = applyCalculations(fields, { a: 3, b: 4, total: 999 });
  assert.equal(out.total, 7, 'applyCalculations scalar');
}

// per-row computed column
{
  const fields: FormField[] = [{
    id: 'items', label: 'Items', type: 'table', required: false, system: false,
    table_config: { row_mode: 'dynamic', columns: [
      { id: 'qty', label: 'Qty', type: 'integer' },
      { id: 'price', label: 'Price', type: 'number' },
      { id: 'line_total', label: 'Line', type: 'number',
        calc: { t: 'binary', op: 'mul', left: { t: 'col', col: 'qty' }, right: { t: 'col', col: 'price' } } },
    ] },
  }];
  const out = applyCalculations(fields, { items: [{ qty: 2, price: 5 }] });
  assert.equal((out.items as Array<Record<string, unknown>>)[0].line_total, 10, 'applyCalculations column');
}

// missing arithmetic operand treated as 0 (the "2 + blank = 2" case)
{
  const fields: FormField[] = [
    numField('number1'), numField('number2'),
    numField('total', { t: 'binary', op: 'add', left: { t: 'field', field: 'number1' }, right: { t: 'field', field: 'number2' } }),
  ];
  const out = applyCalculations(fields, { number1: 2 });
  assert.equal(out.total, 2, 'applyCalculations missing operand as zero');
}

// aggregate field
{
  const fields: FormField[] = [
    { id: 'items', label: 'Items', type: 'table', required: false, system: false,
      table_config: { row_mode: 'dynamic', columns: [{ id: 'amount', label: 'Amt', type: 'number' }] } },
    numField('grand', { t: 'agg', fn: 'sum', table: 'items', column: 'amount' }),
  ];
  const out = applyCalculations(fields, { items: [{ amount: 2 }, { amount: 3 }] });
  assert.equal(out.grand, 5, 'applyCalculations aggregate');
}

// fixed-row matrix cell calcs
{
  const sub = (a: CalcNode, b: CalcNode): CalcNode => ({ t: 'binary', op: 'sub', left: a, right: b });
  const add = (a: CalcNode, b: CalcNode): CalcNode => ({ t: 'binary', op: 'add', left: a, right: b });
  const cellRef = (r: string, c: string): CalcNode => ({ t: 'cell', row: r, col: c });
  const fields: FormField[] = [{
    id: 'financials', label: 'F', type: 'table', required: false, system: false,
    table_config: {
      row_mode: 'fixed',
      columns: [
        { id: 'q1', label: 'Q1', type: 'currency' },
        { id: 'total', label: 'T', type: 'currency' },
      ],
      rows: [
        { id: 'rev', cell_config: {} },
        { id: 'cost', cell_config: {} },
        { id: 'profit', cell_config: {
          q1: { calc: sub(cellRef('rev', 'q1'), cellRef('cost', 'q1')) },
          total: { calc: add(cellRef('profit', 'q1'), cellRef('profit', 'q1')) },
        } },
      ],
    },
  }];
  const out = applyCalculations(fields, { financials: [
    { _row_id: 'rev', q1: 1000 },
    { _row_id: 'cost', q1: 400 },
    { _row_id: 'profit' },
  ] });
  const profit = (out.financials as Array<Record<string, unknown>>).find((r) => r._row_id === 'profit')!;
  assert.equal(profit.q1, 600, 'matrix profit.q1');
  assert.equal(profit.total, 1200, 'matrix profit.total (depends on computed profit.q1)');
}
console.log('applyCalculations checks passed');
