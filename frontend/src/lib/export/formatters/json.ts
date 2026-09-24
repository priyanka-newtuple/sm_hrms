import type { ExportField, ExportRow } from '../types';
import { resolveFieldLabels } from '../fields';

/**
 * Serialize rows to pretty-printed JSON, keyed by human labels. Nested
 * objects/arrays are preserved as real JSON (not stringified). Labels are
 * de-duplicated so no column is silently dropped by a key collision.
 */
export function exportToJson(rows: ExportRow[], fields: ExportField[]): Blob {
  const labels = resolveFieldLabels(fields);
  const objects = rows.map((row) => {
    const obj: Record<string, unknown> = {};
    fields.forEach((f, i) => {
      obj[labels[i]] = row[f.key] ?? null;
    });
    return obj;
  });
  const content = JSON.stringify(objects, null, 2);
  return new Blob([content], { type: 'application/json;charset=utf-8;' });
}
