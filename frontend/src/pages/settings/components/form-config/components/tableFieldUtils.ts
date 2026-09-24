import type { TableColumn, TableColumnType } from '../../../../../core/types';

/** Column type options offered in the table builder. */
export const TABLE_COLUMN_TYPES: { value: TableColumnType; label: string }[] = [
  { value: 'text', label: 'Text' },
  { value: 'textarea', label: 'Text Area' },
  { value: 'integer', label: 'Integer' },
  { value: 'number', label: 'Number' },
  { value: 'currency', label: 'Currency / Amount' },
  { value: 'percent', label: 'Percent' },
  { value: 'date', label: 'Date' },
  { value: 'datetime', label: 'Date & Time' },
  { value: 'select', label: 'Select' },
  { value: 'multi_select', label: 'Multi Select' },
  { value: 'boolean', label: 'Checkbox' },
  { value: 'email', label: 'Email' },
  { value: 'phone', label: 'Phone' },
  { value: 'url', label: 'URL' },
];

/** Slugify a label into a stable column/row id (lowercase, underscores). */
export function toId(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
}

/** Split a comma-separated options string into a trimmed, non-empty list. */
export function splitOptions(value: string): string[] {
  return value.split(',').map((item) => item.trim()).filter(Boolean);
}

/** Coerce a raw cell input into the value shape the column type persists. */
export function normalizeBuilderCellValue(column: TableColumn, raw: string, checked?: boolean): unknown {
  if (column.type === 'boolean') return Boolean(checked);
  if (column.type === 'multi_select') return splitOptions(raw);
  if (raw === '') return '';
  if (column.type === 'integer') return /^-?\d+$/.test(raw) ? Number(raw) : raw;
  if (column.type === 'number' || column.type === 'currency' || column.type === 'percent') {
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : raw;
  }
  return raw;
}

/** Long / multiline / read-only text cells render as a textarea in the builder. */
export function shouldUseFixedRowTextarea(column: TableColumn, value: string): boolean {
  if (column.type === 'textarea') return true;
  if (column.type !== 'text') return false;
  return column.readonly === true || value.length > 80 || value.includes('\n');
}
