import { IDENTIFIER_FIELD_KEY } from './entityForm';

/**
 * Type guard for the currency object shape stored in entity data.
 * Accepts both the canonical form `{ __type: 'currency', amount, currency_code }`
 * and the legacy form that omits `__type` but still carries `amount + currency_code`.
 */
export function isCurrencyObject(value: unknown): value is { amount: unknown; currency_code: unknown } {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  const rec = value as Record<string, unknown>;
  return rec.__type === 'currency' || ('amount' in rec && 'currency_code' in rec);
}

/** A timer_duration field's stored value: whole elapsed seconds, as "3d 4h",
 *  "2h 15m", "12m 30s" or "45s" — matching precision to magnitude, since
 *  something that ran for days doesn't need second-level precision shown. */
export function formatElapsedDuration(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;

  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${secs}s`;
  return `${secs}s`;
}

export function formatCurrencyValue(amount: unknown, code: string): string {
  if (amount !== null && amount !== undefined && amount !== '') {
    const num = typeof amount === 'number' ? amount : parseFloat(String(amount));
    if (!isNaN(num)) {
      try {
        // Fall back to USD when code is absent so Intl.NumberFormat receives a valid currency.
        return new Intl.NumberFormat(undefined, { style: 'currency', currency: code || 'USD' }).format(num);
      } catch {
        return `${code} ${num}`;
      }
    }
  }
  return code || '';
}

const FIELD_VALUE_LABEL_KEYS = [
  'label',
  'name',
  'display_name',
  'title',
  'description',
  'value',
] as const;

function formatEntityFieldListItem(value: unknown): string {
  if (value === null || value === undefined || value === '') return '';
  if (typeof value !== 'object') return String(value);

  const record = value as Record<string, unknown>;

  if (isCurrencyObject(record)) {
    const code = typeof record.currency_code === 'string' ? record.currency_code : '';
    return formatCurrencyValue(record.amount, code);
  }

  for (const key of FIELD_VALUE_LABEL_KEYS) {
    const label = record[key];
    if (label !== null && label !== undefined && label !== '') {
      return formatEntityFieldDisplayValue(label, '');
    }
  }

  try {
    return JSON.stringify(record);
  } catch {
    return String(value);
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

export function getEntityTableDisplayRows(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

export function getEntityTableDisplayColumns(rows: Record<string, unknown>[]): string[] {
  const columns: string[] = [];
  const seen = new Set<string>();
  for (const row of rows) {
    for (const key of Object.keys(row)) {
      if (key.startsWith('_') || seen.has(key)) continue;
      seen.add(key);
      columns.push(key);
    }
  }
  return columns;
}

/**
 * A document field holds file ids, which are meaningless on screen — so
 * anywhere the field type is known, summarise by count instead of leaking a
 * comma-joined list of UUIDs. Surfaces that render values without the field
 * definition (e.g. board column cells) can't call this.
 */
export function formatDocumentFieldValue(value: unknown, empty = '—'): string {
  const count = Array.isArray(value)
    ? value.filter((id) => typeof id === 'string' && id.trim() !== '').length
    : 0;
  if (count === 0) return empty;
  return `${count} ${count === 1 ? 'file' : 'files'}`;
}

export function formatEntityFieldDisplayValue(value: unknown, empty = '—'): string {
  if (value === null || value === undefined || value === '') return empty;
  if (Array.isArray(value)) {
    const items = value.map(formatEntityFieldListItem).filter(Boolean);
    return items.length > 0 ? items.join(', ') : empty;
  }
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value !== 'object') return String(value);
  return formatEntityFieldListItem(value) || empty;
}

/**
 * Derive a single human-readable label for an entity record.
 *
 * Resolution order:
 * 1. The dedicated identifier field (`__identifier`) if it is a non-empty string.
 * 2. The first non-empty string value across all fields.
 * 3. The first non-empty array value, joined by ", ".
 * 4. The first non-empty value of any type — currency objects are formatted via
 *    `formatCurrencyValue`; other objects fall back to `String()`.
 * 5. The first 8 characters of `fallbackId`, or "Untitled entity".
 */
export function getEntityPrimaryValue(
  data: Record<string, unknown> | null | undefined,
  fallbackId?: string,
): string {
  if (data) {
    // Prefer the unique identifier when present.
    const identifier = data[IDENTIFIER_FIELD_KEY];
    if (typeof identifier === 'string' && identifier.trim()) return identifier.trim();

    const values = Object.values(data);
    // Prefer string values first
    for (const value of values) {
      if (typeof value === 'string' && value.trim()) return value.trim();
    }
    // Then arrays
    for (const value of values) {
      if (Array.isArray(value) && value.length > 0) return value.join(', ');
    }
    // Then any non-empty value — format currency objects instead of [object Object]
    for (const value of values) {
      if (value !== null && value !== undefined && value !== '') {
        if (isCurrencyObject(value)) {
          const code = typeof value.currency_code === 'string' ? value.currency_code : '';
          return formatCurrencyValue(value.amount, code);
        }
        return String(value);
      }
    }
  }

  return fallbackId ? fallbackId.slice(0, 8) : 'Untitled entity';
}

const TITLE_KEYS = [IDENTIFIER_FIELD_KEY, 'name', 'title', 'full_name'] as const;

export function getEntityDisplayTitle(
  data: Record<string, unknown> | null | undefined,
  fallbackId: string,
): string {
  if (data) {
    for (const key of TITLE_KEYS) {
      const value = data[key];
      if (typeof value === 'string' && value.trim()) return value.trim();
    }
  }
  return fallbackId;
}
