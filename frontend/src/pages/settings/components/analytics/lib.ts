import type { AnalyticsGroupBy } from '@/core/services/api/analytics';

export const GROUP_OPTIONS: Array<{ value: AnalyticsGroupBy; label: string }> = [
  { value: 'day', label: 'Day' },
  { value: 'week', label: 'Week' },
  { value: 'user', label: 'Person' },
  { value: 'action', label: 'Action' },
  { value: 'category', label: 'Category' },
];

/** "ENTITY_CREATED" -> "Entity Created" for chart/table labels. */
export function humanize(value: string): string {
  return value.toLowerCase().replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}
