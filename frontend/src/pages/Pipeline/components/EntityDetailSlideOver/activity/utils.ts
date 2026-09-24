import type { User } from '@/core/types';
import type { TimelineEvent } from './useActivityTimeline';

/** Formats an ISO timestamp as a human-readable relative time string. */
export function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  if (days < 30) return `${Math.floor(days / 7)}w ago`;
  if (days < 365) return `${Math.floor(days / 30)}mo ago`;
  return `${Math.floor(days / 365)}y ago`;
}

/** Resolves a user ID to a display name using the org user list. */
export function resolveAssigneeName(id: string | null | undefined, orgUsers: User[]): string {
  if (!id) return 'Unassigned';
  const user = orgUsers.find((u) => u.id === id);
  return user?.full_name ?? id.slice(0, 8);
}

/** Returns a human-readable date bucket label (Today / Yesterday / Month Day). */
export function dateBucketLabel(iso: string): string {
  const date = new Date(iso);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  if (date.toDateString() === today.toDateString()) return 'Today';
  if (date.toDateString() === yesterday.toDateString()) return 'Yesterday';
  return date.toLocaleDateString('en-US', { month: 'long', day: 'numeric' });
}

/** Groups a flat list of timeline events into date-labelled buckets. */
export function groupByDate(items: TimelineEvent[]): Array<{ label: string; events: TimelineEvent[] }> {
  const map = new Map<string, TimelineEvent[]>();
  for (const event of items) {
    const label = dateBucketLabel(event.occurredAt);
    const group = map.get(label);
    if (group) group.push(event);
    else map.set(label, [event]);
  }
  return Array.from(map.entries()).map(([label, events]) => ({ label, events }));
}
