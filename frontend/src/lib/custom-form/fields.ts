/**
 * Rendering a custom form's schema against the record's own data.
 *
 * The schema says which fields exist; the values are flat `data` keys. These
 * helpers convert between the two: a fixed grid becomes one table field whose
 * rows carry the answers, and an edit to that grid becomes flat keys again.
 */

import type { CustomFormCell, CustomFormSchema, FormField } from '@/core/types';
import { customFormValueKey, customFormWritableColumns } from '@/core/types';

type Values = Record<string, unknown>;

/** The platform form field one cell renders as. */
export function cellToField(cell: CustomFormCell): FormField {
  return {
    id: cell.id,
    label: cell.label,
    type: cell.type,
    required: false,
    system: false,
    placeholder: cell.placeholder,
    ...(cell.table_config ? { table_config: cell.table_config } : {}),
  } as FormField;
}

/** A grid's rows for display: the schema's own rows with the answers merged in.
 *
 *  Mirrors what FieldInput's `seedRows` builds from a fixed row preset — it
 *  uses a supplied array verbatim, so the line and description columns have to
 *  be carried here too, not just the writable ones. */
export function tableRowsForDisplay(cell: CustomFormCell, values: Values) {
  return (cell.table_config?.rows ?? []).map((row) => {
    const rowId = String(row.id ?? '');
    const answers: Values = {};
    for (const column of customFormWritableColumns(cell, row)) {
      const key = customFormValueKey(cell.id, rowId, String(column.id));
      if (values[key] !== undefined) answers[column.id] = values[key];
    }
    return {
      _row_id: rowId,
      ...(row.line ? { line: row.line, _line: row.line } : {}),
      ...(row.label ? { description: row.label, _label: row.label } : {}),
      ...answers,
    };
  });
}

/** The flat keys an edited grid writes back. */
export function tableRowsToValues(cell: CustomFormCell, rows: unknown): Values {
  if (!Array.isArray(rows)) return {};
  const out: Values = {};
  const presets = cell.table_config?.rows ?? [];
  for (const row of rows) {
    if (!row || typeof row !== 'object') continue;
    const record = row as Record<string, unknown>;
    const rowId = String(record._row_id ?? '');
    if (!rowId) continue;
    const preset = presets.find((item) => String(item.id) === rowId);
    for (const column of customFormWritableColumns(cell, preset)) {
      out[customFormValueKey(cell.id, rowId, String(column.id))] = record[column.id];
    }
  }
  return out;
}

/** One cell's current value, ready to hand to FieldInput. */
export function cellValue(cell: CustomFormCell, values: Values): unknown {
  if (cell.type === 'table' && cell.table_config) return tableRowsForDisplay(cell, values);
  return values[customFormValueKey(cell.id)];
}

/** The flat keys one cell's change writes back. */
export function cellChangeToValues(cell: CustomFormCell, next: unknown): Values {
  if (cell.type === 'table' && cell.table_config) return tableRowsToValues(cell, next);
  return { [customFormValueKey(cell.id)]: next };
}


export interface CustomFormSectionTab {
  key: string;
  label: string;
}

/** Tab keys for one form's sections, for the record's tab strip. */
export function customFormTabs(methodId: string, schema: CustomFormSchema): CustomFormSectionTab[] {
  return (schema.sections ?? []).map((section) => ({
    key: `custom:${methodId}:${section.id}`,
    label: section.title || 'Section',
  }));
}

/** Read a `custom:<methodId>:<sectionId>` tab key back apart. */
export function parseCustomFormTabKey(
  key: string | undefined,
): { methodId: string; sectionId: string } | null {
  if (!key?.startsWith('custom:')) return null;
  const [, methodId, ...rest] = key.split(':');
  const sectionId = rest.join(':');
  return methodId && sectionId ? { methodId, sectionId } : null;
}
