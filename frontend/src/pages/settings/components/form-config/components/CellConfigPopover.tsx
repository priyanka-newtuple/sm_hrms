import { useState } from 'react';
import { Sigma } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { cn } from '@/lib/utils';
import CalcBuilder from './CalcBuilder';
import { SegmentedControl } from '@/core/components/SegmentedControl';
import type { CalcNode, TableColumn, TableColumnType } from '../../../../../core/types';

type CellCfg = { type?: TableColumnType; calc?: CalcNode; readonly?: boolean };
type CellMode = 'input' | 'readonly' | 'calculated';

const CELL_TYPES: TableColumnType[] = [
  'text', 'textarea', 'email', 'phone', 'number', 'integer',
  'date', 'datetime', 'select', 'multi_select', 'boolean', 'url', 'percent', 'currency',
];

const MODE_OPTIONS: readonly { value: CellMode; label: string }[] = [
  { value: 'input', label: 'Input' },
  { value: 'readonly', label: 'Read-only' },
  { value: 'calculated', label: 'Calculated' },
];

export interface CellConfigPopoverProps {
  column: TableColumn;
  rowLabel: string;
  value: CellCfg | undefined;
  onChange: (next: CellCfg | undefined) => void;
  cellRows: { id: string; label: string }[];
  cellColumns: { id: string; label: string }[];
}

export default function CellConfigPopover({
  column, rowLabel, value, onChange, cellRows, cellColumns,
}: CellConfigPopoverProps) {
  // Local mode is the source of truth for the toggle — deriving it from
  // value.calc deadlocks (Calculated with no formula yet would snap back).
  const [mode, setModeState] = useState<CellMode>(
    value?.calc ? 'calculated' : value?.readonly ? 'readonly' : 'input',
  );
  const typeBase = value?.type ? { type: value.type } : {};

  const setMode = (next: CellMode) => {
    setModeState(next);
    if (next === 'input') onChange(value?.type ? { type: value.type } : undefined);
    else if (next === 'readonly') onChange({ ...typeBase, readonly: true });
    else onChange({ ...typeBase }); // 'calculated': embedded CalcBuilder emits the formula on mount
  };

  const setType = (t: string) => {
    const type = t === '__same__' ? undefined : (t as TableColumnType);
    const next: CellCfg = { ...value, type };
    if (!type) delete next.type;
    onChange(Object.keys(next).length ? next : undefined);
  };

  const hasCalc = Boolean(value?.calc);
  const typeOverridden = Boolean(value?.type);

  return (
    <Popover>
      <PopoverTrigger
        title="Configure cell"
        aria-label={`Configure cell ${rowLabel} ${column.label || column.id}`}
        className={cn(
          'flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-cobalt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cobalt',
          (hasCalc || typeOverridden) && 'text-cobalt',
        )}
      >
        <Sigma className="h-3.5 w-3.5" />
      </PopoverTrigger>
      <PopoverContent align="end" className="w-96">
        <div className="text-xs font-semibold text-foreground">
          {rowLabel} · {column.label || column.id}
        </div>

        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-muted-foreground">Type</span>
          <select
            value={value?.type ?? '__same__'}
            onChange={(e) => setType(e.target.value)}
            className="w-full rounded-md border border-border bg-card px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-cobalt focus:border-cobalt"
          >
            <option value="__same__">Same as column ({column.type})</option>
            {CELL_TYPES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-muted-foreground">Mode</span>
          <SegmentedControl fill size="sm" options={MODE_OPTIONS} value={mode} onChange={setMode} />
        </div>

        {mode === 'calculated' && (
          <CalcBuilder
            mode="cell"
            embedded
            value={value?.calc}
            onChange={(calc) => onChange({ ...typeBase, calc })}
            numericFields={[]}
            tableFields={[]}
            cellRows={cellRows}
            cellColumns={cellColumns}
          />
        )}
      </PopoverContent>
    </Popover>
  );
}
