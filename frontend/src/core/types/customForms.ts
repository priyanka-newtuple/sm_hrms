/**
 * A custom form's schema, as fetched per record from its method's connector.
 *
 * Structure only. Every answer is an ordinary `entities.data` field, keyed by
 * `customFormValueKey`, so a form's values live beside every other value the
 * record holds and travel through the normal save path.
 */

import type { FieldType, TableColumn, TableFieldConfig } from './index';

/** Joins the parts of a table cell's field key. Not "." — a dot makes the key
 *  look like a path to `$entity.<field>` placeholders and to the server's
 *  source-path reader, both of which split on it. Mirrors
 *  `custom_forms.services.mapping.KEY_SEPARATOR`. */
export const CUSTOM_FORM_KEY_SEPARATOR = '__';

/** The `data` key one answer is stored under. Mirrors
 *  `custom_forms.services.mapping.value_key`. */
export function customFormValueKey(cellId: string, rowId?: string, columnId?: string): string {
  return [cellId, rowId, columnId].filter(Boolean).join(CUSTOM_FORM_KEY_SEPARATOR);
}

export interface CustomFormCell {
  id: string;
  label: string;
  type: FieldType;
  /** False for a display-only cell: never filled and never editable. */
  editable: boolean;
  /** Path into the results body that fills this cell. Resolved server-side;
   *  carried here only so the shape matches what is stored. */
  source?: string;
  /** Present when `type` is 'table' — the grid's columns and fixed rows. */
  table_config?: TableFieldConfig;
  placeholder?: string;
}

export interface CustomFormSection {
  id: string;
  title: string;
  cells: CustomFormCell[];
}

/** The columns a row accepts a value in. A grid marks display-only cells per
 *  row (`readonly_cells`), not only on the column, so both are checked. */
export function customFormWritableColumns(
  cell: CustomFormCell,
  row?: { readonly_cells?: string[] },
): TableColumn[] {
  const locked = new Set(row?.readonly_cells ?? []);
  return (cell.table_config?.columns ?? []).filter(
    (column) => !column.readonly && !locked.has(String(column.id)),
  );
}

export interface CustomFormSchema {
  sections: CustomFormSection[];
  /** Cross-cell formulas, by target key. Empty for a form with none. */
  calculations?: Record<string, unknown>;
}

/** Every `data` key this schema's answers occupy, for seeding a draft and for
 *  letting them past the schema-driven save filter. */
export function customFormValueKeys(schema: CustomFormSchema): string[] {
  const keys: string[] = [];
  for (const section of schema.sections ?? []) {
    for (const cell of section.cells ?? []) {
      const config = cell.table_config;
      if (cell.type === 'table' && config) {
        for (const row of config.rows ?? []) {
          for (const column of customFormWritableColumns(cell, row)) {
            keys.push(customFormValueKey(cell.id, String(row.id), String(column.id)));
          }
        }
        continue;
      }
      keys.push(customFormValueKey(cell.id));
    }
  }
  return keys;
}
