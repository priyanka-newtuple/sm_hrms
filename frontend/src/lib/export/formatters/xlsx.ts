import * as XLSX from 'xlsx';
import type { ExportField, ExportRow } from '../types';
import { resolveFieldLabels } from '../fields';

const XLSX_MIME =
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

/**
 * Convert a value to an Excel cell. Primitives (number, boolean, string) are
 * kept native so Excel can type them correctly; objects/arrays are JSON-encoded;
 * null/undefined become an empty string. String cells stay text — SheetJS does
 * not interpret a leading "=" as a formula, so no injection guard is needed.
 */
function xlsxCell(value: unknown): string | number | boolean {
  if (value === null || value === undefined) return '';
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  if (typeof value === 'number' || typeof value === 'boolean') return value;
  return String(value);
}

/** Serialize rows to a native Excel (.xlsx) workbook. */
export function exportToXlsx(rows: ExportRow[], fields: ExportField[]): Blob {
  const labels = resolveFieldLabels(fields);
  const aoa: (string | number | boolean)[][] = [
    labels,
    ...rows.map((row) => fields.map((f) => xlsxCell(row[f.key]))),
  ];
  const worksheet = XLSX.utils.aoa_to_sheet(aoa);
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, worksheet, 'Export');
  const buffer = XLSX.write(workbook, { bookType: 'xlsx', type: 'array' });
  return new Blob([buffer], { type: XLSX_MIME });
}
