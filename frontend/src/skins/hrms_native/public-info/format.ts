// Helpers for published HR content. Records come from /hrms/public/content or /hrms/content and
// contain only the server's display-field allowlist; every value is rendered as plain text.
export type Published = Record<string, unknown> & { id: string; entity_type: string };

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export const text = (value: unknown) => (typeof value === 'string' ? value.trim() : typeof value === 'number' ? String(value) : '');

/** YYYY-MM-DD values are calendar dates, so format them in UTC to avoid off-by-one days. */
export function toDate(value: unknown): Date | null {
  const raw = text(value);
  return ISO_DATE.test(raw) ? new Date(`${raw}T00:00:00Z`) : null;
}

const fmt = (options: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat(undefined, { timeZone: 'UTC', ...options });
export const formatDate = (date: Date) => fmt({ day: 'numeric', month: 'short', year: 'numeric' }).format(date);
export const formatDay = (date: Date) => fmt({ day: '2-digit' }).format(date);
export const formatMonth = (date: Date) => fmt({ month: 'short' }).format(date);
export const formatMonthLong = (date: Date) => fmt({ month: 'long' }).format(date);
export const formatWeekday = (date: Date) => fmt({ weekday: 'long' }).format(date);

export const todayIso = () => new Date().toISOString().slice(0, 10);

/** Days from today (UTC calendar) to the given date; 0 means today. */
export function daysUntil(date: Date) {
  const today = new Date(`${todayIso()}T00:00:00Z`);
  return Math.round((date.getTime() - today.getTime()) / 86_400_000);
}

/** Only HTTPS links without embedded credentials are rendered, matching the cockpit's publishing rule. */
export function safeUrl(value: unknown): string | null {
  const raw = text(value);
  try {
    const url = new URL(raw);
    return url.protocol === 'https:' && !url.username && !url.password ? url.toString() : null;
  } catch {
    return null;
  }
}

export interface Holiday { date: Date; iso: string; name: string }

/** Holiday calendars hold one `YYYY-MM-DD | Holiday name` per line; malformed lines are skipped. */
export function parseHolidays(value: unknown): Holiday[] {
  return text(value).split('\n').flatMap(line => {
    const [iso = '', ...rest] = line.split('|').map(part => part.trim());
    const date = toDate(iso);
    const name = rest.join(' | ');
    return date && name ? [{ date, iso, name }] : [];
  }).sort((a, b) => a.iso.localeCompare(b.iso));
}

export const splitList = (value: unknown) => text(value).split(/[,\n]/).map(part => part.trim()).filter(Boolean);

export function matches(record: Published, query: string) {
  if (!query) return true;
  const haystack = ['title', 'body', 'department', 'location', 'trainer', 'skills', 'work_mode', 'holidays'].map(key => text(record[key])).join(' ').toLowerCase();
  return haystack.includes(query.toLowerCase());
}
