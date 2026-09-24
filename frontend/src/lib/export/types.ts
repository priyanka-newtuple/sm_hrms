/** Supported export file formats. */
export type ExportFormat = 'csv' | 'xlsx' | 'json' | 'pdf';

/** A single selectable export column derived from the data. */
export interface ExportField {
  /** Stable key: raw key for system fields, `data.<k>` for data fields. */
  key: string;
  /** Human-readable column header. */
  label: string;
  /** Which group the field belongs to in the picker. */
  group: 'system' | 'data';
  /** How many rows have a non-empty value for this field. */
  fillCount: number;
  /** Total number of rows considered. */
  totalCount: number;
}

/** A flattened row keyed by `ExportField.key`. */
export type ExportRow = Record<string, unknown>;
