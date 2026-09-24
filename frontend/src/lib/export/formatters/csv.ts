import type { ExportField, ExportRow } from '../types';
import { resolveFieldLabels } from '../fields';
import { serializeCellValue } from '../serialize';

// Excel/Sheets treat a cell beginning with one of these as a formula. Prefixing
// a single quote neutralizes formula/CSV injection while displaying the value.
const FORMULA_TRIGGERS = /^[=+\-@\t\r]/;

function sanitizeForFormula(s: string): string {
  if (!FORMULA_TRIGGERS.test(s)) return s;
  // A genuine number (e.g. "-5", "+5", "1e3") is safe — only quote values that
  // aren't numeric, so real formulas like "=SUM(..)" or "-5+3" get neutralized.
  if (s !== '' && !Number.isNaN(Number(s))) return s;
  return `'${s}`;
}

function escapeCsvCell(value: unknown): string {
  const s = sanitizeForFormula(serializeCellValue(value));
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/**
 * Serialize rows to CSV text (CRLF line endings, RFC-4180 escaping). A UTF-8
 * BOM is prepended so Excel renders non-ASCII characters correctly, and cells
 * are guarded against spreadsheet formula injection.
 */
export function exportToCsv(rows: ExportRow[], fields: ExportField[]): Blob {
  const labels = resolveFieldLabels(fields);
  const header = labels.map((l) => escapeCsvCell(l)).join(',');
  const body = rows.map((row) => fields.map((f) => escapeCsvCell(row[f.key])).join(','));
  const BOM = '﻿';
  const content = BOM + [header, ...body].join('\r\n');
  return new Blob([content], { type: 'text/csv;charset=utf-8;' });
}
