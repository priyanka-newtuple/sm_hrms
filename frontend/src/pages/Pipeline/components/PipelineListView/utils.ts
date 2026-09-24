import { humanize } from '@/shared/utils/labels';

/** Format an ISO timestamp as e.g. "Jun 3, 2026". */
export function formatDate(iso: string): string {
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(new Date(iso));
}

/** Turn a snake/kebab field key into a Title Case label: `tenant_name` → `Tenant Name`.
 *  Delegates to the platform-wide {@link humanize} formatter. */
export const titleCase = humanize;

/** Compare two cell values: numbers numerically, everything else as text, nulls last. */
export function compareValues(a: unknown, b: unknown): number {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  return String(a).localeCompare(String(b), undefined, { numeric: true });
}
