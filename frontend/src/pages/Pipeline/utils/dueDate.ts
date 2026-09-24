import type { PipelineListEntity } from '@/shared/types/pipeline';

export interface ScheduledEntity {
  entity: PipelineListEntity;
  date: Date;
}

export function parseDueDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  const parsed = dateOnly
    ? new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]))
    : new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export interface DueDatePresentation {
  label: string;
  status: 'overdue' | 'today' | 'upcoming';
}

export function getDueDatePresentation(
  value: string | null | undefined,
  today = new Date(),
): DueDatePresentation | null {
  const dueDate = parseDueDate(value);
  if (!dueDate) return null;
  const dueDay = new Date(dueDate.getFullYear(), dueDate.getMonth(), dueDate.getDate()).getTime();
  const currentDay = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
  return {
    label: new Intl.DateTimeFormat('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    }).format(dueDate),
    status: dueDay < currentDay ? 'overdue' : dueDay === currentDay ? 'today' : 'upcoming',
  };
}

function localDateKey(date: Date): string {
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, '0'),
    String(date.getDate()).padStart(2, '0'),
  ].join('-');
}

export function bucketEntitiesByDueDate(
  entities: PipelineListEntity[],
): { byDay: Map<string, ScheduledEntity[]>; unscheduled: number } {
  const byDay = new Map<string, ScheduledEntity[]>();
  let unscheduled = 0;
  for (const entity of entities) {
    const date = parseDueDate(entity.due_date);
    if (!date) {
      unscheduled += 1;
      continue;
    }
    const key = localDateKey(date);
    const bucket = byDay.get(key) ?? [];
    bucket.push({ entity, date });
    byDay.set(key, bucket);
  }
  for (const bucket of byDay.values()) {
    bucket.sort((a, b) => a.date.getTime() - b.date.getTime());
  }
  return { byDay, unscheduled };
}
