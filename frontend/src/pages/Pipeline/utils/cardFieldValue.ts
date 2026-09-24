import type { LucideIcon } from 'lucide-react';
import { CalendarClock, CheckCircle2, Circle, Hash, Paperclip } from 'lucide-react';
import {
  formatCurrencyValue,
  formatDocumentFieldValue,
  formatElapsedDuration,
  isCurrencyObject,
} from '@/shared/utils/entityDisplay';
import { picklistLabel, getAvatarColorClass } from '@/core/utils';

export interface CardFieldMeta {
  type?: string;
  enum_values?: string[];
  enum_labels?: string[];
}

/** How one configured field renders as a card chip: the text, plus an
 *  optional icon or colored dot. Configured fields are entirely user-defined
 *  — the org can name a field anything — so an icon is keyed strictly off
 *  the field's *type*, applied the same way to every field of that type
 *  regardless of its name: every date field gets the same calendar icon,
 *  every number field the same hash icon, etc. It never assumes what a
 *  field means (e.g. that a number field must be a count), only what kind
 *  of value it holds. Select/multi-select fields get a colored dot instead
 *  of an icon — a stable per-value color (hashed the same way avatar colors
 *  are), used purely so distinct values stay visually distinguishable. */
export interface CardFieldRender {
  text: string;
  icon?: LucideIcon;
  dotClassName?: string;
}

const SHORT_DATE_FORMATTER = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' });

/** Map one stored multi_select value to its label via enum_values/enum_labels
 *  (same lookup `picklistLabel` does for a single value) — falls back to the
 *  raw stored value so an option removed from the field's config since a
 *  record was saved still shows something instead of vanishing silently. */
function multiSelectItemLabel(field: CardFieldMeta | undefined, item: unknown): string {
  const label = picklistLabel(field, item);
  return label ?? String(item);
}

/** Compact, single-line rendering of one configured Kanban card field.
 *  Returns null for an empty value so the card can skip the row entirely
 *  rather than showing a bare dash — a summary card has no room for filler.
 *  Long text is left untruncated here; the caller clips with CSS so
 *  truncation adapts to the card's actual width.
 *
 *  Not every field *type* can render as one meaningful compact value —
 *  `section` (a layout placeholder, not real data) and `table`/`picklist_multi`
 *  (structured/composite values with no honest single-line form) are disabled
 *  in the picker itself (`useCardFieldsConfig`), so a newly-selected field is
 *  never one of these. The explicit null below is only a safety net for a
 *  field that was selected before that rule existed, or one type-changed
 *  after being selected — never silently render a `[object Object]`-style
 *  value for those. */
export function formatCardFieldValue(field: CardFieldMeta | undefined, value: unknown): CardFieldRender | null {
  if (value === null || value === undefined || value === '') return null;
  if (Array.isArray(value) && value.length === 0) return null;
  if (field?.type === 'section' || field?.type === 'table' || field?.type === 'picklist_multi') return null;

  if (field?.type === 'multi_select' && Array.isArray(value)) {
    const labels = value.map((item) => multiSelectItemLabel(field, item));
    return { text: labels.join(', '), dotClassName: getAvatarColorClass(labels.join(',')) };
  }

  const picklist = picklistLabel(field, value);
  if (picklist !== null) return { text: picklist, dotClassName: getAvatarColorClass(String(value)) };

  if (isCurrencyObject(value)) {
    const record = value;
    const code = typeof record.currency_code === 'string' ? record.currency_code : '';
    return { text: formatCurrencyValue(record.amount, code) };
  }

  if ((field?.type === 'date' || field?.type === 'datetime') && typeof value === 'string') {
    const parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime())) return { text: SHORT_DATE_FORMATTER.format(parsed), icon: CalendarClock };
  }

  if (field?.type === 'timer_duration' && typeof value === 'number') {
    return { text: formatElapsedDuration(value) };
  }

  if (field?.type === 'document') {
    const text = formatDocumentFieldValue(value, '');
    return text ? { text, icon: Paperclip } : null;
  }

  if (field?.type === 'integer' || field?.type === 'number') {
    return { text: String(value), icon: Hash };
  }

  if (typeof value === 'boolean') {
    return { text: value ? 'Yes' : 'No', icon: value ? CheckCircle2 : Circle };
  }

  if (Array.isArray(value)) return { text: value.map((item) => String(item)).join(', ') };
  if (typeof value === 'object') return null;
  return { text: String(value) };
}
