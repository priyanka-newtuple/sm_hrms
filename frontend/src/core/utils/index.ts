/**
 * Core Utilities
 */

export { getIcon, hasIcon, getAvailableIcons } from './iconMap';
export { parseRemoteMcpServerId } from './remoteMcp';
import { AVATAR_COLORS } from './avatarColors';
import { formatCurrencyValue, isCurrencyObject } from '../../shared/utils/entityDisplay';

// Platform org — users here with admin role are treated as super-admins
const PLATFORM_ORG_ID = '00000000-0000-0000-0000-000000000000';

export const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function isSuperAdminUser(
  user: { role?: string; organizationId?: string } | null | undefined
): boolean {
  // Must match the Platform org — a tenant org's own "superadmin" role
  // (any org can grant this to its own users) is not platform-wide and
  // must not satisfy this check. Mirrors require_platform_permission in
  // backend/common/auth.py, which checks the role within PLATFORM_ORG_ID.
  return (
    user?.organizationId === PLATFORM_ORG_ID &&
    (user?.role === 'superadmin' || user?.role === 'admin')
  );
}

// Mirrors the backend's ADMIN_ALLOWED_ROLES (backend/common/auth.py) — keep in sync
// if that list ever changes.
export function isAdminRole(role: string | undefined): boolean {
  return role === 'admin' || role === 'superadmin' || role === 'owner';
}

const ISO_DATETIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/;

// A rich-text field (RichTextEditor) stores its value as raw HTML — cheap
// sniff for that shape without touching plain strings that merely contain a
// literal "<" or ">".
const LOOKS_LIKE_HTML = /<(p|div|span|ol|ul|li|br|strong|em|b|i|h[1-6]|a)\b[^>]*>/i;

export function stripHtmlForPreview(value: string): string {
  if (!LOOKS_LIKE_HTML.test(value)) return value;
  const text = new DOMParser().parseFromString(value, 'text/html').body.textContent ?? '';
  return text.replace(/\s+/g, ' ').trim();
}

/** True when a value should be rendered right-aligned (numeric column). */
export function isNumericValue(value: unknown): boolean {
  return typeof value === 'number' && Number.isFinite(value);
}

/**
 * Format a number compactly for axis ticks and KPI labels: 1_250 → "1.3K",
 * 2_400_000 → "2.4M". Small values (< 1000) keep their locale form.
 */
export function formatCompactNumber(value: number): string {
  if (!Number.isFinite(value)) return '—';
  const abs = Math.abs(value);
  if (abs < 1000) {
    return Number.isInteger(value) ? value.toLocaleString() : value.toLocaleString(undefined, { maximumFractionDigits: 1 });
  }
  return value.toLocaleString(undefined, { notation: 'compact', maximumFractionDigits: 1 });
}

/**
 * Percentage change from `prev` to `current`. Returns null when there is no
 * meaningful baseline (no previous value, or a zero baseline with no change).
 */
export function percentChange(current: number, prev: number | undefined): number | null {
  if (prev == null || !Number.isFinite(prev)) return null;
  if (prev === 0) return current === 0 ? 0 : null;
  return ((current - prev) / Math.abs(prev)) * 100;
}

/** First letter of first and last name, or first two chars for a single word. */
export function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
  return name.substring(0, 2).toUpperCase();
}

/** Deterministic background color class based on a user id, so the same
 *  person always gets the same avatar color everywhere in the app. */
export function getAvatarColorClass(userId: string): string {
  let hash = 0;
  for (let i = 0; i < userId.length; i++) {
    hash = userId.charCodeAt(i) + ((hash << 5) - hash);
  }
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

/** Map a stored select/multi_select value to its display label via enum_values/enum_labels.
 *  Returns null when the field has no label map or the value isn't found. */
export function picklistLabel(
  field: { type?: string; enum_values?: string[]; enum_labels?: string[] } | undefined,
  value: unknown,
): string | null {
  if (!field || !field.enum_values?.length) return null;
  // When type is present, restrict to select/multi_select. When absent (e.g.
  // ColumnField), trust that enum_values being set is enough.
  if (field.type && field.type !== 'select' && field.type !== 'multi_select') return null;
  const i = field.enum_values.indexOf(String(value));
  if (i !== -1) return field.enum_labels?.[i] ?? String(value);
  return null;
}

/** Render any table cell value as a human-readable string. */
export function formatTableCell(value: unknown): string {
  if (value == null) return '—';
  if (typeof value === 'string') {
    if (ISO_DATETIME.test(value)) {
      const d = new Date(value);
      if (!Number.isNaN(d.getTime())) {
        return d.toLocaleString(undefined, {
          year: 'numeric',
          month: 'short',
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
        });
      }
    }
    return stripHtmlForPreview(value);
  }
  if (typeof value === 'number') return value.toLocaleString();
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (isCurrencyObject(value)) {
    const code = typeof value.currency_code === 'string' ? value.currency_code : '';
    return formatCurrencyValue(value.amount, code) || '—';
  }
  if (Array.isArray(value)) {
    const items = (value as unknown[])
      .map((item) => (item == null ? '' : typeof item === 'object' ? formatTableCell(item) : String(item)))
      .filter(Boolean);
    return items.length > 0 ? items.join(', ') : '—';
  }
  return JSON.stringify(value);
}
