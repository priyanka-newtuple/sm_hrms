import { Plus, X } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import PicklistMultiWizard from './PicklistMultiWizard';
import DocumentFieldInput from './DocumentFieldInput';
import TimerDurationField from './TimerDurationField';
import type { FormField, TableColumn } from '../types';
import { resolveCellType, isCellComputedOrReadonly } from '../../shared/utils/calc';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { PhoneInput } from './Phone-input';
import RichTextEditor from './RichTextEditor';
import { CURRENCIES } from '../constants/currencies';
import { parseCurrencyValue } from '../../shared/utils/entityForm';

const BASE = 'h-auto w-full px-4 py-3 border rounded-xl text-base';
const borderClass = (invalid?: boolean) =>
  invalid
    ? 'border-destructive focus:ring-2 focus:ring-destructive focus:border-destructive'
    : 'border-border focus:ring-2 focus:ring-cobalt focus:border-cobalt';

type TableRow = Record<string, unknown>;

function createTableRowId(fieldId: string): string {
  const randomId = globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2);
  return `${fieldId}_row_${randomId}`;
}

function seedRows(field: FormField, value: unknown): TableRow[] {
  if (Array.isArray(value)) return value.filter((row): row is TableRow => Boolean(row) && typeof row === 'object' && !Array.isArray(row));
  const config = field.table_config;
  if (config?.row_mode !== 'fixed') return [];
  return (config.rows ?? []).map((row) => ({
    _row_id: row.id,
    ...(row.line ? { line: row.line, _line: row.line } : {}),
    ...(row.label ? { description: row.label, _label: row.label } : {}),
    ...(row.cells ?? {}),
  }));
}

function normalizeTableCell(column: TableColumn, raw: string, checked?: boolean): unknown {
  if (column.type === 'boolean') return Boolean(checked);
  if (column.type === 'multi_select') return raw;
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

export default function FieldInput({
  field,
  value,
  onChange,
  disabled = false,
  invalid = false,
  entityId,
  documentPreviewEnabled = false,
  timerCanStop,
  timerStopBlockedHint,
  onTimerStopped,
  timerLocalStartedAt,
  onTimerLocalStart,
  onTimerLocalStop,
}: {
  field: FormField;
  value: unknown;
  onChange: (v: unknown) => void;
  disabled?: boolean;
  invalid?: boolean;
  /** The record this field belongs to. Document uploads are stored unowned
   *  when absent; a timer cannot persist until the record exists. */
  entityId?: string;
  /** Enables document previews in surfaces that render the shared preview panel. */
  documentPreviewEnabled?: boolean;
  /** timer_duration only — see TimerDurationField for what each one does.
   *  All optional, so every other caller is unaffected. */
  timerCanStop?: boolean;
  timerStopBlockedHint?: string;
  onTimerStopped?: (elapsedSeconds: number) => void | Promise<void>;
  timerLocalStartedAt?: number | null;
  onTimerLocalStart?: () => void;
  onTimerLocalStop?: () => void;
}) {
  const cls = cn(BASE, borderClass(invalid));

  if (field.type === 'timer_duration') {
    return (
      <TimerDurationField
        fieldKey={field.id}
        value={value}
        onChange={onChange}
        entityId={entityId}
        disabled={disabled}
        canStop={timerCanStop}
        stopBlockedHint={timerStopBlockedHint}
        onStopped={onTimerStopped}
        localStartedAt={timerLocalStartedAt}
        onLocalStart={onTimerLocalStart}
        onLocalStop={onTimerLocalStop}
      />
    );
  }

  if (field.type === 'document') {
    return (
      <DocumentFieldInput
        field={field}
        value={value}
        onChange={onChange}
        disabled={disabled}
        invalid={invalid}
        entityId={entityId}
        showPreview={documentPreviewEnabled}
      />
    );
  }

  if (field.calc) {
    const shown = value === null || value === undefined || value === '' ? '—' : String(value);
    return (
      <div className="px-4 py-3 border rounded-xl border-border bg-muted/50 text-foreground text-base">
        {shown}
      </div>
    );
  }

  if (field.type === 'boolean') {
    return (
      <Switch
        checked={!!value}
        onCheckedChange={(checked) => onChange(checked)}
        disabled={disabled}
        aria-invalid={invalid}
        size="lg"
      />
    );
  }

  if (field.type === 'auto_number') {
    const cfg = field.auto_number_config ?? {};
    const placeholder = (() => {
      const core = 'xxxx';
      if (cfg.affix && cfg.affix_mode === 'prefix') return `${cfg.affix}-${core}`;
      if (cfg.affix && cfg.affix_mode === 'suffix') return `${core}-${cfg.affix}`;
      return core;
    })();
    return (
      <div className="px-4 py-3 border rounded-xl border-border bg-muted/50 text-muted-foreground font-mono text-sm">
        {value ? String(value) : placeholder}
      </div>
    );
  }

  if (field.type === 'select') {
    return (
      <select value={String(value ?? '')} onChange={(e) => onChange(e.target.value)} disabled={disabled} aria-invalid={invalid} className={cls}>
        <option value="">Select…</option>
        {(field.enum_values ?? []).map((opt, i) => (
          <option key={opt} value={opt}>{field.enum_labels?.[i] ?? opt}</option>
        ))}
      </select>
    );
  }

  if (field.type === 'multi_select') {
    const selected = Array.isArray(value) ? (value as string[]) : [];
    const toggle = (opt: string) =>
      onChange(
        selected.includes(opt) ? selected.filter((v) => v !== opt) : [...selected, opt]
      );
    return (
      <div className={cn('flex flex-wrap gap-2 rounded-lg border px-3 pt-4 pb-2.5 min-h-[42px]', invalid ? 'border-destructive' : 'border-border')}>

        {(field.enum_values ?? []).map((opt, i) => (
          <button
            key={opt}
            type="button"
            onClick={() => !disabled && toggle(opt)}
            disabled={disabled}
            className={`px-3 py-1 rounded-full text-sm border transition-colors ${
              selected.includes(opt)
                ? 'bg-cobalt text-white border-cobalt'
                : 'border-border text-foreground hover:border-cobalt'
            }`}
          >
            {field.enum_labels?.[i] ?? opt}
          </button>
        ))}
      </div>
    );
  }

  if (field.type === 'table') {
    const columns = field.table_config?.columns ?? [];
    const rowMode = field.table_config?.row_mode ?? 'dynamic';
    const displayMode = field.table_config?.display_mode ?? 'grid';
    const allowDelete = field.table_config?.allow_delete_rows ?? rowMode === 'dynamic';
    const maxRows = field.table_config?.max_rows;
    const rows = seedRows(field, value);
    const displayRows = rowMode === 'fixed'
      ? (rows.length > 0 ? rows : seedRows(field, undefined))
      : rows;
    const canAdd = !disabled && rowMode === 'dynamic' && (!maxRows || displayRows.length < maxRows);

    const commit = (next: TableRow[]) => onChange(next);
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
      const readonly = disabled || cellReadonly(field, row, rowIndex, column);
      const cellClass = cn(
        mode === 'grid'
          ? 'h-full min-h-10 w-full rounded-none border-0 bg-transparent px-2 py-1.5 text-sm outline-none focus:bg-card focus:ring-2 focus:ring-cobalt'
          : 'w-full rounded-lg border px-2.5 py-2 text-sm outline-none',
        mode === 'grid'
          ? readonly ? 'text-muted-foreground' : 'text-foreground'
          : readonly ? 'border-border bg-muted/50 text-muted-foreground' : borderClass(invalid),
      );
      const textLikeReadonly =
        readonly &&
        (column.type === 'text' ||
          column.type === 'email' ||
          column.type === 'phone' ||
          column.type === 'url');
      // Colour overrides are offered on text and text-area columns only, the
      // same two types the column editor exposes them for.
      const cellStyle =
        column.type === 'text' || column.type === 'textarea'
          ? {
              backgroundColor: column.style_config?.background_color,
              color: column.style_config?.text_color,
            }
          : undefined;

      if (column.type === 'boolean') {
        return (
          <div className={mode === 'grid' ? 'flex min-h-10 items-center justify-center' : undefined}>
            <input
              type="checkbox"
              checked={Boolean(value)}
              disabled={readonly}
              onChange={(e) => updateCell(rowIndex, column, e.target.checked)}
              className="h-4 w-4 rounded border-border text-cobalt focus:ring-cobalt"
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
            className={cellClass}
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
          <div className={cn(
            'flex flex-wrap gap-1.5 px-2 py-1.5',
            mode === 'grid' ? 'min-h-10 rounded-none border-0 bg-transparent' : 'min-w-[180px] rounded-lg border',
            mode === 'grid' ? '' : readonly ? 'border-border bg-muted/50' : 'border-border bg-card',
          )}>
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
                  className={cn(
                    'rounded-full border px-2 py-0.5 text-xs',
                    active ? 'border-cobalt bg-cobalt text-white' : 'border-border text-foreground',
                  )}
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
            placeholder={column.placeholder}
            disabled={readonly}
            onChange={(e) => updateCell(rowIndex, column, e.target.value)}
            style={cellStyle}
            className={cn(cellClass, mode === 'grid' ? 'min-h-10 resize-y' : 'min-w-[220px] resize-y')}
          />
        );
      }
      if (textLikeReadonly) {
        return (
          <div
            style={cellStyle}
            className={cn(
              'min-h-10 w-full px-2.5 py-2 text-sm text-muted-foreground whitespace-normal break-words',
              mode === 'grid' ? 'bg-transparent' : 'rounded-lg border border-border bg-muted/50',
            )}
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
            placeholder={column.placeholder}
            disabled={readonly}
            onChange={(e) => updateCell(rowIndex, column, e.target.value)}
            style={cellStyle}
            className={cn(cellClass, 'min-h-10 resize-y whitespace-normal break-words')}
          />
        );
      }

      const inputType =
        column.type === 'date' ? 'date' :
        column.type === 'datetime' ? 'datetime-local' :
        column.type === 'email' ? 'email' :
        column.type === 'url' ? 'url' :
        column.type === 'phone' ? 'tel' :
        column.type === 'integer' || column.type === 'number' || column.type === 'currency' || column.type === 'percent' ? 'number' :
        'text';
      return (
        <input
          type={inputType}
          value={String(value ?? '')}
          placeholder={column.placeholder}
          disabled={readonly}
          onChange={(e) => updateCell(rowIndex, column, normalizeTableCell(column, e.target.value))}
          style={cellStyle}
          className={cellClass}
        />
      );
    };

    if (displayMode === 'form') {
      return (
        <div className={cn('rounded-xl border bg-card', invalid ? 'border-destructive' : 'border-border')}>
          <div className="divide-y divide-border">
            {displayRows.length === 0 ? (
              <div className="px-3 py-6 text-center text-sm text-muted-foreground">No rows yet.</div>
            ) : displayRows.map((row, rowIndex) => (
              <div key={String(row._row_id ?? rowIndex)} className="p-3">
                {displayRows.length > 1 && (
                  <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Row {rowIndex + 1}
                  </div>
                )}
                <div className="grid grid-cols-2 gap-3">
                {columns.map((column) => (
                  <div key={column.id} className={cn('space-y-1', tableFormFieldClass(column))}>
                    <label className="block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      {column.label}
                      {column.required && <span className="ml-0.5 text-destructive">*</span>}
                    </label>
                    {renderCell(row, rowIndex, column, 'form')}
                  </div>
                ))}
                </div>
                {!disabled && allowDelete && rowMode === 'dynamic' && (
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
                className="inline-flex items-center gap-1 rounded-lg border border-border bg-card px-2.5 py-1.5 text-sm font-medium text-cobalt hover:border-cobalt/40"
              >
                <Plus size={14} />
                Add row
              </button>
            </div>
          )}
        </div>
      );
    }

    return (
      <div className={cn('rounded-xl border bg-card', invalid ? 'border-destructive' : 'border-border')}>
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
                {!disabled && allowDelete && rowMode === 'dynamic' && <th className="w-10 border border-border px-3 py-2" />}
              </tr>
            </thead>
            <tbody>
              {displayRows.length === 0 ? (
                <tr>
                  <td colSpan={columns.length + 3} className="px-3 py-6 text-center text-sm text-muted-foreground">
                    No rows yet.
                  </td>
                </tr>
              ) : displayRows.map((row, rowIndex) => (
                <tr key={String(row._row_id ?? rowIndex)}>
                  {columns.map((column) => (
                    <td key={column.id} className="w-56 border border-border bg-card p-0 align-top whitespace-normal break-words">
                      {renderCell(row, rowIndex, column, 'grid')}
                    </td>
                  ))}
                  {!disabled && allowDelete && rowMode === 'dynamic' && (
                    <td className="border border-border px-2 py-1 align-middle">
                      <button
                        type="button"
                        onClick={() => removeRow(rowIndex)}
                        className="rounded-lg p-1 text-muted-foreground hover:bg-muted hover:text-destructive"
                        title="Remove row"
                      >
                        <X size={16} />
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
              className="inline-flex items-center gap-1 rounded-lg border border-border bg-card px-2.5 py-1.5 text-sm font-medium text-cobalt hover:border-cobalt/40"
            >
              <Plus size={14} />
              Add row
            </button>
          </div>
        )}
      </div>
    );
  }

  if (field.type === 'picklist_multi') {
    return (
      <PicklistMultiWizard
        field={field}
        value={value}
        onChange={onChange}
        disabled={disabled}
        invalid={invalid}
        entityId={entityId}
      />
    );
  }

  if (field.type === 'phone') {
    return (
      <PhoneInput
        value={String(value ?? '')}
        onChange={onChange}
        placeholder={field.placeholder}
        disabled={disabled}
        required={field.required}
        autoComplete="tel"
        aria-invalid={invalid}
        inputClassName={cls}
        countrySelectClassName={invalid ? 'border-destructive' : undefined}
      />
    );
  }

  if (field.type === 'textarea') {
    return (
      <RichTextEditor
        value={String(value ?? '')}
        onChange={(html) => onChange(html)}
        placeholder={field.placeholder}
        disabled={disabled}
        invalid={invalid}
        backgroundColor={field.style_config?.background_color}
        textColor={field.style_config?.text_color}
      />
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
      onChange({ __type: 'currency', amount: newAmount, currency_code: newCode });
    };

    return (
      <div className={cn(
        'flex items-stretch overflow-hidden rounded-xl border',
        invalid
          ? 'border-destructive focus-within:ring-2 focus-within:ring-destructive'
          : 'border-border focus-within:border-cobalt focus-within:ring-2 focus-within:ring-cobalt',
      )}>
        <select
          value={currencyCode}
          disabled={disabled}
          onChange={(e) => emitChange(amountStr, e.target.value)}
          className="shrink-0 border-r border-border bg-muted/50 px-3 py-3 text-sm font-medium text-foreground focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
        >
          {CURRENCIES.map((c) => (
            <option key={c.code} value={c.code}>{c.code}</option>
          ))}
        </select>
        <input
          type="text"
          inputMode="decimal"
          value={amountStr}
          placeholder={field.placeholder ?? '0.00'}
          disabled={disabled}
          aria-invalid={invalid}
          className="min-w-0 flex-1 bg-transparent px-4 py-3 text-base outline-none disabled:cursor-not-allowed disabled:opacity-50"
          onKeyDown={(e) => {
            const allowed = ['Backspace', 'Delete', 'ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Tab', 'Enter', 'Home', 'End', '.'];
            if (allowed.includes(e.key)) return;
            if ((e.ctrlKey || e.metaKey) && ['a', 'c', 'x', 'z'].includes(e.key.toLowerCase())) return;
            if (!/^[\d]$/.test(e.key)) e.preventDefault();
          }}
          onPaste={(e) => {
            const text = e.clipboardData.getData('text');
            if (!/^\d*\.?\d*$/.test(text.trim())) e.preventDefault();
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

  if (field.type === 'integer') {
    return (
      <Input
        type="text"
        inputMode="numeric"
        value={String(value ?? '')}
        placeholder={field.placeholder}
        disabled={disabled}
        aria-invalid={invalid}
        className={cls}
        onKeyDown={(e) => {
          const allowed = ['Backspace', 'Delete', 'ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Tab', 'Enter', 'Home', 'End'];
          if (allowed.includes(e.key)) return;
          if ((e.ctrlKey || e.metaKey) && ['a', 'c', 'x', 'z'].includes(e.key.toLowerCase())) return;
          if (!/^[\d-]$/.test(e.key)) e.preventDefault();
        }}
        onPaste={(e) => {
          const text = e.clipboardData.getData('text');
          if (!/^-?\d+$/.test(text.trim())) e.preventDefault();
        }}
        onChange={(e) => {
          const raw = e.target.value;
          if (raw === '' || raw === '-') onChange(raw);
          else if (/^-?\d+$/.test(raw)) onChange(Number(raw));
        }}
      />
    );
  }

  const inputType =
    field.type === 'number' ? 'number' :
    field.type === 'date' || field.type === 'datetime' ? 'datetime-local' :
    field.type === 'email' ? 'email' :
    field.type === 'url' ? 'url' :
    'text';

  return (
    <Input
      type={inputType}
      value={String(value ?? '')}
      required={field.required}
      autoComplete={
        field.type === 'email' ? 'email' : field.type === 'url' ? 'url' : undefined
      }
      onChange={(e) =>
        onChange(
          field.type === 'number' && e.target.value !== ''
            ? Number(e.target.value)
            : e.target.value
        )
      }
      placeholder={field.placeholder}
      disabled={disabled}
      aria-invalid={invalid}
      className={cls}
      style={{
        backgroundColor: field.style_config?.background_color,
        color: field.style_config?.text_color,
      }}
    />
  );
}
