import { formatDistanceToNow, isToday } from 'date-fns';
import type { EntityType } from '../../../core/types';

const ICON_PALETTE = [
  'bg-sky-50 text-sky-600',
  'bg-emerald-50 text-emerald-600',
  'bg-amber-50 text-amber-600',
  'bg-violet-50 text-violet-600',
  'bg-rose-50 text-rose-600',
  'bg-cyan-50 text-cyan-600',
  'bg-lime-50 text-lime-700',
];

export function normalizeRecordEntityType(value: string): string {
  return value.replace(/^ATS\./i, '').trim().toLowerCase();
}

export function latestEntityTypesByName(entityTypes: EntityType[]): EntityType[] {
  const latestByName = new Map<string, EntityType>();
  for (const entityType of entityTypes) {
    const key = normalizeRecordEntityType(entityType.name);
    const existing = latestByName.get(key);
    if (!existing || (entityType.version ?? 0) > (existing.version ?? 0)) {
      latestByName.set(key, entityType);
    }
  }
  return Array.from(latestByName.values());
}

export function entityTypeCardKey(entityType: EntityType): string {
  return entityType.entity_type_id ?? entityType.id ?? normalizeRecordEntityType(entityType.name);
}

function hashString(value: string): number {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash << 5) - hash + value.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}

export function iconClassFor(name: string): string {
  return ICON_PALETTE[hashString(name) % ICON_PALETTE.length];
}

export function formatCount(count: number): string {
  return count.toLocaleString('en-US');
}

export function formatUpdatedAt(value: string | null | undefined): string {
  if (!value) return 'never';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'unknown';
  if (isToday(date)) return 'today';
  return `${formatDistanceToNow(date)} ago`
    .replace('about ', '')
    .replace('less than a minute', '1m')
    .replace(' minutes', 'm')
    .replace(' minute', 'm')
    .replace(' hours', 'h')
    .replace(' hour', 'h')
    .replace(' days', 'd')
    .replace(' day', 'd')
    .replace(' months', 'mo')
    .replace(' month', 'mo')
    .replace(' years', 'y')
    .replace(' year', 'y');
}
