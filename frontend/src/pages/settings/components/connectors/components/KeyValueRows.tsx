import { Plus, X } from 'lucide-react';

import type { KeyValueRow } from '../types';

interface KeyValueRowsProps {
  rows: KeyValueRow[];
  onChange: (rows: KeyValueRow[]) => void;
  keyPlaceholder: string;
  valuePlaceholder: string;
  onValueFocus?: (index: number) => void;
}

/** Editable list of free-text {key, value} rows (used for headers and query params). Pure UI. */
export default function KeyValueRows({
  rows,
  onChange,
  keyPlaceholder,
  valuePlaceholder,
  onValueFocus,
}: KeyValueRowsProps) {
  const updateRow = (index: number, patch: Partial<KeyValueRow>) =>
    onChange(rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  const removeRow = (index: number) => onChange(rows.filter((_, i) => i !== index));
  const addRow = () => onChange([...rows, { key: '', value: '' }]);

  return (
    <div className="space-y-2">
      {rows.map((row, index) => (
        <div key={index} className="flex items-center gap-2">
          <input
            value={row.key}
            onChange={(e) => updateRow(index, { key: e.target.value })}
            placeholder={keyPlaceholder}
            className="h-8 flex-1 rounded-md border border-input bg-background px-2 font-mono text-xs"
          />
          <input
            value={row.value}
            onChange={(e) => updateRow(index, { value: e.target.value })}
            onFocus={() => onValueFocus?.(index)}
            placeholder={valuePlaceholder}
            className="h-8 flex-1 rounded-md border border-input bg-background px-2 font-mono text-xs"
          />
          <button
            type="button"
            onClick={() => removeRow(index)}
            className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-muted"
            aria-label="Remove row"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={addRow}
        className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
      >
        <Plus className="h-3.5 w-3.5" /> Add row
      </button>
    </div>
  );
}
