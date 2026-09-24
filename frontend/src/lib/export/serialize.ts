/**
 * Convert an arbitrary entity value to a flat string for text-based exports
 * (CSV, PDF). Objects and arrays — which appear in entity data (e.g. a
 * `documents` array) — are JSON-encoded instead of becoming "[object Object]".
 * `null`/`undefined` become an empty string; primitives are stringified as-is
 * (so `false` → "false", `0` → "0").
 */

import { humanize } from '@/shared/utils/labels';

/**
 * Flatten one picklist_multi row's "Extend Field" values.
 *
 * Field keys are humanized rather than looked up: an export renders a value
 * with no access to the field configuration that holds the authored labels.
 */
function serializeExtensions(raw: unknown): string {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return '';
  return Object.entries(raw as Record<string, unknown>)
    .map(([option, values]) => {
      if (!values || typeof values !== 'object' || Array.isArray(values)) return '';
      const pairs = Object.entries(values as Record<string, unknown>)
        .map(([key, value]) => {
          const flat = serializeCellValue(value);
          return flat ? `${humanize(key)}: ${flat}` : '';
        })
        .filter(Boolean)
        .join('; ');
      return pairs ? `${option} — ${pairs}` : '';
    })
    .filter(Boolean)
    .join('; ');
}
export function serializeCellValue(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'object') {
    // Handle picklist_multi: array of {dropdown, toggles} objects
    if (Array.isArray(value) && value.length > 0) {
      const first = value[0];
      if (first && typeof first === 'object' && 'dropdown' in first && 'toggles' in first) {
        return (value as unknown[])
          .map((row) => {
            const r = row as Record<string, unknown>;
            const dropdown = String(r.dropdown || '');
            const toggles = Array.isArray(r.toggles) ? (r.toggles as string[]) : [];
            const toggleStr = toggles.join(', ');
            const base = dropdown && toggleStr ? `${dropdown}: ${toggleStr}` : dropdown || toggleStr || '';
            const extended = serializeExtensions(r.extensions);
            return extended ? `${base} (${extended})` : base;
          })
          .filter(Boolean)
          .join(' | ');
      }
    }
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}
