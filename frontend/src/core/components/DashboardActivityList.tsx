/**
 * DashboardActivityList
 *
 * Renders a `rows` payload of audit-log events (from the events.activity metric)
 * as a compact timeline: icon + human title + relative time + actor, with an
 * expandable details row. Reads well-known row keys (event_type, entity_type,
 * actor_type/id/name, before_state, after_state, occurred_at). No data fetching.
 */
import { useState } from 'react';
import {
  Activity,
  CheckCircle2,
  ChevronDown,
  FileText,
  Zap,
  type LucideIcon,
} from 'lucide-react';
import { resolveEntityTypeLabel, resolveEnumLabel, resolveStateLabel } from '@/shared/utils/labels';

interface Row {
  event_type?: string;
  entity_type?: string | null;
  entity_id?: string | null;
  entity_identifier?: string | null;
  actor_type?: string | null;
  actor_id?: string | null;
  actor_name?: string | null;
  before_state?: string | null;
  after_state?: string | null;
  occurred_at?: string | null;
}

const ACTOR_TYPE_USER = 'user';

function iconFor(eventType: string): LucideIcon {
  if (eventType === 'ENTITY_ENROLLED') return FileText;
  if (eventType.startsWith('STATE') || eventType.startsWith('TRANSITION')) return CheckCircle2;
  if (eventType.startsWith('TASK') || eventType.startsWith('ACTION')) return Zap;
  return Activity;
}

function titleFor(r: Row): string {
  const entity = r.entity_type ? resolveEntityTypeLabel(r.entity_type) : 'Record';
  switch (r.event_type) {
    case 'STATE_TRANSITIONED':
    case 'TRANSITION_SUCCEEDED':
      return r.after_state
        ? `${entity} moved to ${resolveStateLabel(r.after_state)}`
        : `${entity} state changed`;
    case 'TRANSITION_BLOCKED':
      return `${entity} transition blocked`;
    case 'ENTITY_ENROLLED':
      return `${entity} created`;
    case 'TASK_EXECUTED':
      return `Task executed on ${entity}`;
    default:
      return `${resolveEnumLabel(r.event_type ?? 'event')} · ${entity}`;
  }
}

function relativeTime(iso: string | null | undefined): string {
  if (!iso) return '';
  const secs = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (secs < 60) return 'just now';
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins} minute${mins === 1 ? '' : 's'} ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? '' : 's'} ago`;
}

function ActivityItem({ r }: { r: Row }) {
  const [open, setOpen] = useState(false);
  const Icon = iconFor(r.event_type ?? '');
  const actor = r.actor_type === ACTOR_TYPE_USER ? (r.actor_name ?? 'Deleted user') : (r.actor_type ?? 'System');
  return (
    <li className="flex gap-2.5 border-b border-border py-2.5 last:border-0">
      <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
        <Icon className="h-3.5 w-3.5" strokeWidth={1.5} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium text-foreground">{titleFor(r)}</div>
        <div className="text-xs text-muted-foreground">
          {relativeTime(r.occurred_at)} · {actor}
        </div>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="mt-1 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        >
          <ChevronDown
            className={open ? 'h-3.5 w-3.5 rotate-180 transition' : 'h-3.5 w-3.5 transition'}
            strokeWidth={1.5}
          />
          Details
        </button>
        {open && (
          <dl className="mt-1 grid grid-cols-[max-content_1fr] gap-x-2 gap-y-0.5 rounded-md bg-muted/40 p-2 text-xs">
            <dt className="text-muted-foreground">Event</dt>
            <dd className="text-foreground">{r.event_type}</dd>
            {r.before_state && (
              <>
                <dt className="text-muted-foreground">From</dt>
                <dd className="text-foreground">{r.before_state}</dd>
              </>
            )}
            {r.after_state && (
              <>
                <dt className="text-muted-foreground">To</dt>
                <dd className="text-foreground">{r.after_state}</dd>
              </>
            )}
            {r.entity_id && (
              <>
                <dt className="text-muted-foreground">Entity</dt>
                <dd className="truncate text-foreground">
                  {r.entity_type} · {r.entity_identifier ?? r.entity_id}
                </dd>
              </>
            )}
          </dl>
        )}
      </div>
    </li>
  );
}

export default function DashboardActivityList({ rows }: { rows: Record<string, unknown>[] }) {
  if (!rows || rows.length === 0) {
    return <div className="text-sm text-muted-foreground">No activity yet</div>;
  }
  return (
    <ul className="h-full overflow-y-auto pr-1">
      {rows.map((r, i) => (
        <ActivityItem key={(r.entity_id as string) ?? i} r={r as Row} />
      ))}
    </ul>
  );
}

export type { Row as ActivityRowData };
