import { Plus, X } from 'lucide-react';

import type { KeyFieldRow } from '../types';

const CUSTOM = '__custom__';

interface MappingRowsProps {
  rows: KeyFieldRow[];
  onChange: (rows: KeyFieldRow[]) => void;
  keyLabel: string;
  keyPlaceholder: string;
  fieldLabel: string;
  fieldOptions: string[];
}

/** Editable list of {free-text key ↔ entity field (or custom value)} rows. Pure UI. */
export default function MappingRows({
  rows,
  onChange,
  keyLabel,
  keyPlaceholder,
  fieldLabel,
  fieldOptions,
}: MappingRowsProps) {
  const updateRow = (index: number, patch: Partial<KeyFieldRow>) => {
    onChange(rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  };

  const selectField = (index: number, value: string) => {
    if (value === CUSTOM) updateRow(index, { custom: true, field: '' });
    else updateRow(index, { custom: false, field: value });
  };

  const removeRow = (index: number) => onChange(rows.filter((_, i) => i !== index));
  const addRow = () => onChange([...rows, { key: '', field: '' }]);

  return (
    <div className="space-y-2">
      {rows.length > 0 && (
        <div className="flex gap-2 text-[11px] font-medium text-muted-foreground">
          <span className="flex-1">{keyLabel}</span>
          <span className="flex-1">{fieldLabel}</span>
          <span className="w-7" />
        </div>
      )}
      {rows.map((row, index) => (
        <div key={index} className="flex items-start gap-2">
          <input
            value={row.key}
            onChange={(e) => updateRow(index, { key: e.target.value })}
            placeholder={keyPlaceholder}
            className="h-8 flex-1 rounded-md border border-input bg-background px-2 font-mono text-xs"
          />
          <div className="flex-1 space-y-1">
            <select
              value={row.custom ? CUSTOM : row.field}
              onChange={(e) => selectField(index, e.target.value)}
              className="h-8 w-full rounded-md border border-input bg-background px-2 text-xs"
            >
              <option value="">Select field…</option>
              {fieldOptions.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
              <option value={CUSTOM}>Custom value…</option>
            </select>
            {row.custom && (
              <input
                value={row.field}
                onChange={(e) => updateRow(index, { field: e.target.value })}
                placeholder="Custom value (supports {{field}})"
                className="h-8 w-full rounded-md border border-input bg-background px-2 font-mono text-xs"
              />
            )}
          </div>
          <button
            type="button"
            onClick={() => removeRow(index)}
            className="flex h-8 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-muted"
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
