import { useRef, useState } from 'react';

import type { FormField, TableColumn } from '../../../core/types';
import { PhoneInput } from '../../../core/components/Phone-input';
import { CURRENCIES } from '../../../core/constants/currencies';
import { parseCurrencyValue } from '../../../shared/utils/entityForm';
import { resolveCellType, isCellComputedOrReadonly } from '../../../shared/utils/calc';

const inputCls = (hasError: boolean) =>
  `w-full rounded-xl border px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground bg-card outline-none transition
  ${hasError
    ? 'border-destructive/30 focus:border-destructive/30 focus:ring-2 focus:ring-destructive/15'
    : 'border-border focus:border-info/30 focus:ring-2 focus:ring-info/15'}`;

type TableRow = Record<string, unknown>;

function createTableRowId(fieldId: string): string {
  const randomId = globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2);
  return `${fieldId}_row_${randomId}`;
}

function seedRows(field: FormField, value: unknown): TableRow[] {
  if (Array.isArray(value)) return value.filter((row): row is TableRow => Boolean(row) && typeof row === 'object' && !Array.isArray(row));
  if (field.table_config?.row_mode !== 'fixed') return [];
  return (field.table_config.rows ?? []).map((row) => ({
    _row_id: row.id,
    ...(row.line ? { line: row.line, _line: row.line } : {}),
    ...(row.label ? { description: row.label, _label: row.label } : {}),
    ...(row.cells ?? {}),
  }));
}

function normalizeCell(column: TableColumn, raw: string): unknown {
  if (raw === '') return '';
  if (column.type === 'integer') return /^-?\d+$/.test(raw) ? Number(raw) : raw;
  if (column.type === 'number' || column.type === 'currency' || column.type === 'percent') {
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : raw;
  }
  return raw;
}

function cellReadonly(field: FormField, row: TableRow, rowIndex: number, column: TableColumn): boolean {
  if (isCellComputedOrReadonly(field, row, column)) return true;
  if (column.calc) return true;
  if (column.readonly) return true;
  const rowId = String(row._row_id ?? '');
  const preset = field.table_config?.rows?.find((item, index) => item.id === rowId || index === rowIndex);
  return Boolean(preset?.readonly || preset?.readonly_cells?.includes(column.id));
}

function tableFormFieldClass(column: TableColumn): string {
  return column.type === 'textarea' || column.readonly ? 'col-span-2' : 'col-span-2 md:col-span-1';
}

export function FieldInput({
  field,
  value,
  hasError,
  onChange,
}: {
  field: FormField;
  value: unknown;
  hasError: boolean;
  onChange: (id: string, value: unknown) => void;
}) {
  const [intError, setIntError] = useState<string | null>(null);
  const intTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  if (field.type === 'boolean') {
    return (
      <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-border bg-muted/50 px-4 py-3 transition hover:border-info/30 hover:bg-info-subtle/30">
        <input
          type="checkbox"
          checked={Boolean(value)}
          onChange={(e) => onChange(field.id, e.target.checked)}
          className="mt-0.5 h-4 w-4 shrink-0 cursor-pointer rounded border-border accent-blue-600"
        />
        <span className="text-sm text-foreground">{field.placeholder || 'Check to confirm'}</span>
      </label>
    );
  }

  if (field.type === 'multi_select') {
    const selected = Array.isArray(value) ? (value as string[]) : [];
    const options = field.enum_values ?? [];
    const toggle = (opt: string) =>
      onChange(
        field.id,
        selected.includes(opt) ? selected.filter((v) => v !== opt) : [...selected, opt],
      );
    if (options.length === 0) {
      return (
        <input
          type="text"
          value={typeof value === 'string' ? value : ''}
          onChange={(e) => onChange(field.id, e.target.value)}
          className={inputCls(hasError)}
          placeholder="Enter a value"
        />
      );
    }
    return (
      <div className="flex flex-wrap gap-2">
        {options.map((opt) => (
          <button
            key={opt}
            type="button"
            onClick={() => toggle(opt)}
            className={`rounded-full border px-3.5 py-1.5 text-sm font-medium transition ${
              selected.includes(opt)
                ? 'border-info/30 bg-info text-info-foreground shadow-sm'
                : 'border-border bg-card text-foreground hover:border-info/30 hover:text-info'
            }`}
          >
            {opt}
          </button>
        ))}
      </div>
    );
  }

  if (field.type === 'select') {
    const options = field.enum_values ?? [];
    if (options.length === 0) {
      return (
        <input
          type="text"
          value={typeof value === 'string' ? value : ''}
          onChange={(e) => onChange(field.id, e.target.value)}
          className={inputCls(hasError)}
          placeholder="Enter a value"
        />
      );
    }
    return (
      <select
        value={typeof value === 'string' ? value : ''}
        required={field.required}
        onChange={(e) => onChange(field.id, e.target.value)}
        className={inputCls(hasError)}
      >
        <option value="">Select an option…</option>
        {options.map((opt) => (
          <option key={opt} value={opt}>{opt}</option>
        ))}
      </select>
    );
  }

  if (field.type === 'table') {
    const columns = field.table_config?.columns ?? [];
    const rowMode = field.table_config?.row_mode ?? 'dynamic';
    const displayMode = field.table_config?.display_mode ?? 'grid';
    const allowDelete = field.table_config?.allow_delete_rows ?? rowMode === 'dynamic';
    const rows = seedRows(field, value);
    const displayRows = rowMode === 'fixed'
      ? (rows.length > 0 ? rows : seedRows(field, undefined))
      : rows;
    const maxRows = field.table_config?.max_rows;
    const canAdd = rowMode === 'dynamic' && (!maxRows || displayRows.length < maxRows);

    const commit = (next: TableRow[]) => onChange(field.id, next);
    const updateCell = (rowIndex: number, column: TableColumn, nextValue: unknown) => {
      commit(displayRows.map((row, index) => (
        index === rowIndex ? { ...row, [column.id]: nextValue } : row
      )));
    };
    const addRow = () => {
      const row: TableRow = { _row_id: createTableRowId(field.id) };
      columns.forEach((column) => {
        row[column.id] = column.type === 'boolean' ? false : column.type === 'multi_select' ? [] : '';
      });
      commit([...displayRows, row]);
    };
    const removeRow = (rowIndex: number) => commit(displayRows.filter((_, index) => index !== rowIndex));
    const renderCell = (row: TableRow, rowIndex: number, columnDef: TableColumn, mode: 'grid' | 'form' = 'form') => {
      const column: TableColumn = { ...columnDef, type: resolveCellType(field, row, columnDef) };
      const value = row[column.id];
      const readonly = cellReadonly(field, row, rowIndex, column);
      const controlClass = mode === 'grid'
        ? 'h-full min-h-10 w-full rounded-none border-0 bg-transparent px-2 py-1.5 text-sm text-foreground outline-none focus:bg-card focus:ring-2 focus:ring-info/15'
        : inputCls(hasError);
      if (column.type === 'boolean') {
        return (
          <div className={mode === 'grid' ? 'flex min-h-10 items-center justify-center' : undefined}>
            <input
              type="checkbox"
              checked={Boolean(value)}
              disabled={readonly}
              onChange={(e) => updateCell(rowIndex, column, e.target.checked)}
              className="h-4 w-4 rounded border-border accent-blue-600"
            />
          </div>
        );
      }
      if (column.type === 'select') {
        return (
          <select
            value={String(value ?? '')}
            disabled={readonly}
            onChange={(e) => updateCell(rowIndex, column, e.target.value)}
            className={controlClass}
          >
            <option value="">Select...</option>
            {(column.enum_values ?? []).map((option) => (
              <option key={option} value={option}>{option}</option>
            ))}
          </select>
        );
      }
      if (column.type === 'multi_select') {
        const selected = Array.isArray(value) ? value.map(String) : [];
        return (
          <div className={mode === 'grid'
            ? 'flex min-h-10 flex-wrap gap-1.5 bg-transparent px-2 py-1.5'
            : 'flex min-w-[180px] flex-wrap gap-1.5 rounded-lg border border-border bg-card px-2 py-1.5'}
          >
            {(column.enum_values ?? []).map((option) => {
              const active = selected.includes(option);
              return (
                <button
                  key={option}
                  type="button"
                  disabled={readonly}
                  onClick={() => updateCell(
                    rowIndex,
                    column,
                    active ? selected.filter((item) => item !== option) : [...selected, option],
                  )}
                  className={`rounded-full border px-2 py-0.5 text-xs ${
                    active
                      ? 'border-info/30 bg-info text-info-foreground'
                      : 'border-border bg-card text-foreground'
                  }`}
                >
                  {option}
                </button>
              );
            })}
          </div>
        );
      }
      if (column.type === 'textarea') {
        return (
          <textarea
            rows={2}
            value={String(value ?? '')}
            disabled={readonly}
            onChange={(e) => updateCell(rowIndex, column, e.target.value)}
            className={`${controlClass} ${mode === 'grid' ? 'min-h-10' : 'min-w-[220px]'} resize-y`}
          />
        );
      }
      if (readonly && ['text', 'email', 'phone', 'url'].includes(column.type)) {
        return (
          <div className={mode === 'grid'
            ? 'min-h-10 w-full bg-transparent px-2.5 py-2 text-sm text-muted-foreground whitespace-normal break-words'
            : 'min-h-10 w-full rounded-lg border border-border bg-muted/50 px-2.5 py-2 text-sm text-muted-foreground whitespace-normal break-words'}
          >
            {String(value ?? '') || '—'}
          </div>
        );
      }
      if (mode === 'grid' && column.type === 'text') {
        return (
          <textarea
            rows={2}
            value={String(value ?? '')}
            disabled={readonly}
            onChange={(e) => updateCell(rowIndex, column, e.target.value)}
            className={`${controlClass} min-h-10 resize-y whitespace-normal break-words`}
          />
        );
      }
      return (
        <input
          type={
            column.type === 'date' ? 'date' :
            column.type === 'datetime' ? 'datetime-local' :
            column.type === 'email' ? 'email' :
            column.type === 'url' ? 'url' :
            column.type === 'phone' ? 'tel' :
            ['integer', 'number', 'currency', 'percent'].includes(column.type) ? 'number' :
            'text'
          }
          value={String(value ?? '')}
          disabled={readonly}
          onChange={(e) => updateCell(rowIndex, column, normalizeCell(column, e.target.value))}
          className={controlClass}
        />
      );
    };

    if (displayMode === 'form') {
      return (
        <div className={`rounded-xl border bg-card ${hasError ? 'border-destructive/30' : 'border-border'}`}>
          <div className="divide-y divide-border">
            {displayRows.length === 0 ? (
              <div className="px-3 py-6 text-center text-muted-foreground">No rows yet.</div>
            ) : displayRows.map((row, rowIndex) => (
              <div key={String(row._row_id ?? rowIndex)} className="p-3">
                {displayRows.length > 1 && (
                  <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Row {rowIndex + 1}
                  </div>
                )}
                <div className="grid grid-cols-2 gap-3">
                {columns.map((column) => (
                  <div key={column.id} className={`space-y-1 ${tableFormFieldClass(column)}`}>
                    <label className="block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      {column.label}
                      {column.required && <span className="ml-0.5 text-destructive">*</span>}
                    </label>
                    {renderCell(row, rowIndex, column, 'form')}
                  </div>
                ))}
                </div>
                {allowDelete && rowMode === 'dynamic' && (
                  <div className="flex justify-end">
                    <button
                      type="button"
                      onClick={() => removeRow(rowIndex)}
                      className="rounded-lg px-2 py-1 text-sm text-muted-foreground hover:bg-muted hover:text-destructive"
                    >
                      Remove row
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
          {canAdd && (
            <div className="border-t border-border px-3 py-2">
              <button
                type="button"
                onClick={addRow}
                className="rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-medium text-info hover:border-info/30"
              >
                Add row
              </button>
            </div>
          )}
        </div>
      );
    }

    return (
      <div className={`rounded-xl border bg-card ${hasError ? 'border-destructive/30' : 'border-border'}`}>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] table-fixed border-collapse text-sm">
            <thead>
              <tr className="bg-muted/50 text-left text-xs font-semibold uppercase text-muted-foreground">
                {columns.map((column) => (
                  <th key={column.id} className="w-56 border border-border px-3 py-2 whitespace-normal break-words">
                    {column.label}
                    {column.required && <span className="ml-0.5 text-destructive">*</span>}
                  </th>
                ))}
                {allowDelete && rowMode === 'dynamic' && <th className="w-10 border border-border px-3 py-2" />}
              </tr>
            </thead>
            <tbody>
              {displayRows.length === 0 ? (
                <tr>
                  <td colSpan={columns.length + 3} className="px-3 py-6 text-center text-muted-foreground">
                    No rows yet.
                  </td>
                </tr>
              ) : displayRows.map((row, rowIndex) => (
                <tr key={String(row._row_id ?? rowIndex)}>
                  {columns.map((column) => {
                    return (
                      <td key={column.id} className="w-56 border border-border bg-card p-0 align-top whitespace-normal break-words">
                        {renderCell(row, rowIndex, column, 'grid')}
                      </td>
                    );
                  })}
                  {allowDelete && rowMode === 'dynamic' && (
                    <td className="border border-border px-2 py-1">
                      <button
                        type="button"
                        onClick={() => removeRow(rowIndex)}
                        className="rounded-lg px-2 py-1 text-muted-foreground hover:bg-muted hover:text-destructive"
                      >
                        Remove
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {canAdd && (
          <div className="border-t border-border px-3 py-2">
            <button
              type="button"
              onClick={addRow}
              className="rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-medium text-info hover:border-info/30"
            >
              Add row
            </button>
          </div>
        )}
      </div>
    );
  }

  if (field.type === 'currency') {
    const defaultCode = field.currency_config?.currency_code ?? 'USD';
    const cv = parseCurrencyValue(value);
    const currencyCode = typeof cv?.currency_code === 'string' ? cv.currency_code : defaultCode;
    const amountStr = cv !== null
      ? (cv.amount !== null && cv.amount !== undefined ? String(cv.amount) : '')
      : (value !== null && value !== undefined ? String(value) : '');

    const emitChange = (newAmount: string | number, newCode: string) => {
      onChange(field.id, { __type: 'currency', amount: newAmount, currency_code: newCode });
    };

    return (
      <div className={`flex items-stretch overflow-hidden rounded-xl border ${hasError ? 'border-destructive/30 focus-within:ring-2 focus-within:ring-destructive/30' : 'border-border focus-within:border-info/30 focus-within:ring-2 focus-within:ring-info/30'}`}>
        <select
          value={currencyCode}
          onChange={(e) => emitChange(amountStr, e.target.value)}
          className="shrink-0 border-r border-border bg-muted/50 px-3 py-3 text-sm font-medium text-foreground focus:outline-none"
        >
          {CURRENCIES.map((c) => (
            <option key={c.code} value={c.code}>{c.code}</option>
          ))}
        </select>
        <input
          type="text"
          inputMode="decimal"
          value={amountStr}
          required={field.required}
          placeholder={field.placeholder ?? '0.00'}
          className="min-w-0 flex-1 bg-transparent px-4 py-3 text-base outline-none"
          onKeyDown={(e) => {
            const allowed = ['Backspace', 'Delete', 'ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Tab', 'Enter', 'Home', 'End', '.'];
            if (allowed.includes(e.key)) return;
            if ((e.ctrlKey || e.metaKey) && ['a', 'c', 'x', 'z'].includes(e.key.toLowerCase())) return;
            if (!/^[\d]$/.test(e.key)) e.preventDefault();
          }}
          onPaste={(e) => {
            if (!/^\d*\.?\d*$/.test(e.clipboardData.getData('text').trim())) e.preventDefault();
          }}
          onChange={(e) => {
            const raw = e.target.value;
            if (raw === '' || raw === '.') { emitChange(raw, currencyCode); return; }
            if (/^\d*\.?\d*$/.test(raw)) emitChange(raw, currencyCode);
          }}
          onBlur={(e) => {
            const raw = e.target.value;
            if (raw === '' || raw === '.') return;
            const parsed = parseFloat(raw);
            if (!isNaN(parsed)) emitChange(parsed, currencyCode);
          }}
        />
      </div>
    );
  }

  if (field.type === 'textarea') {
    return (
      <textarea
        rows={4}
        value={typeof value === 'string' ? value : ''}
        required={field.required}
        onChange={(e) => onChange(field.id, e.target.value)}
        className={`${inputCls(hasError)} resize-y`}
        placeholder={field.placeholder ?? ''}
      />
    );
  }

  if (field.type === 'integer') {
    const showError = hasError || Boolean(intError);
    return (
      <div>
        <input
          type="text"
          inputMode="numeric"
          value={String(value ?? '')}
          required={field.required}
          placeholder={field.placeholder ?? 'Enter a whole number'}
          className={inputCls(showError)}
          onKeyDown={(e) => {
            const nav = ['Backspace', 'Delete', 'ArrowLeft', 'ArrowRight', 'Tab', 'Enter', 'Home', 'End'];
            if (nav.includes(e.key) || ((e.ctrlKey || e.metaKey) && 'acxz'.includes(e.key))) return;
            if (!/^[\d-]$/.test(e.key)) {
              e.preventDefault();
              setIntError('Numbers only');
              if (intTimer.current) clearTimeout(intTimer.current);
              intTimer.current = setTimeout(() => setIntError(null), 3000);
            }
          }}
          onPaste={(e) => {
            if (!/^-?\d+$/.test(e.clipboardData.getData('text').trim())) {
              e.preventDefault();
              setIntError('Numbers only');
            }
          }}
          onChange={(e) => {
            const raw = e.target.value;
            setIntError(null);
            if (raw === '' || raw === '-') onChange(field.id, raw);
            else if (/^-?\d+$/.test(raw)) onChange(field.id, Number(raw));
          }}
        />
        {intError && <p className="mt-1.5 text-xs text-destructive">{intError}</p>}
      </div>
    );
  }

  if (field.type === 'phone') {
    return (
      <PhoneInput
        value={typeof value === 'string' ? value : ''}
        required={field.required}
        autoComplete="tel"
        aria-invalid={hasError}
        onChange={(nextValue) => onChange(field.id, nextValue)}
        inputClassName={inputCls(hasError)}
        countrySelectClassName={hasError ? 'border-destructive/30' : 'border-border'}
        placeholder={field.placeholder ?? ''}
      />
    );
  }

  const typeMap: Record<string, string> = {
    email: 'email', url: 'url',
    datetime: 'datetime-local', date: 'date', number: 'number',
  };

  return (
    <input
      type={typeMap[field.type] ?? 'text'}
      value={typeof value === 'string' || typeof value === 'number' ? String(value) : ''}
      required={field.required}
      autoComplete={field.type === 'email' ? 'email' : field.type === 'url' ? 'url' : undefined}
      onChange={(e) => onChange(field.id, e.target.value)}
      className={inputCls(hasError)}
      placeholder={field.placeholder ?? ''}
    />
  );
}
