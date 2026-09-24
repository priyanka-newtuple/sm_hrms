import { useInfiniteQuery } from '@tanstack/react-query';
import { events as eventsApi } from '@/core/services/api/events';
import { timelineKeys } from '@/core/services/api/queryKeys';
import { env } from '@/skins/skin.config';
import type { AuditEventResponse } from '@/core/types';
import type { TimelineEventKind } from '../constants';

const PAGE_SIZE = env.timelinePageSize;

// ── Unified event type ────────────────────────────────────────────────────────

export interface TimelineEvent {
  id: string;
  kind: TimelineEventKind;
  occurredAt: string;
  actorName: string | null;
  actorRole: string | null;
  fromState?: string;
  toState?: string;
  trigger?: string;
  blockedReasons?: string[];
  changedFieldCount?: number;
  changedFieldNames?: string[];
  unresolvedSourceCount?: number;
  previousAssigneeId?: string | null;
  newAssigneeId?: string | null;
  actionKind?: string;
  /** Snapshot taken when the action was configured — fed to useActionDisplayNames. */
  actionDisplayName?: string;
  errorMessage?: string;
  /** What a completed action reports it did. An action can finish successfully
   *  without doing the obvious thing — declining to assign a suspended user,
   *  say — and the headline alone cannot tell those apart. */
  outcomeMessage?: string;
  /** "manual_rerun" when a user re-ran the state action from the detail view. */
  triggerSource?: string;
  triggeredById?: string | null;
  /** Chain position, e.g. index 1 of total 3 renders "(2/3)". */
  actionIndex?: number;
  actionTotal?: number;
  chainReason?: string;
}

// ── Normalization ─────────────────────────────────────────────────────────────

interface EventMetadataFields {
  trigger?: string;
  task?: string;
  blocked_reasons?: string[];
  changed_fields?: Record<string, unknown>;
  previous_assignee_id?: string | null;
  new_assignee_id?: string | null;
  action_kind?: string;
  action_display_name?: string;
  error?: string;
  message?: string;
  refused?: boolean;
  trigger_source?: string;
  triggered_by?: string;
  action_index?: number;
  action_total?: number;
  reason?: string;
  filled_fields?: string[];
  unresolved_sources?: string[];
}

/** Runtime-checks the shape of `metadata` (an untyped JSONB blob on the wire)
 * before any field is trusted. A field with an unexpected type comes back as
 * `undefined` — same as "field absent" everywhere it's consumed below — rather
 * than an unchecked cast silently propagating a wrong value into the UI. */
function readEventMetadata(raw: unknown): EventMetadataFields {
  const obj = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  const isStringArray = (v: unknown): v is string[] =>
    Array.isArray(v) && v.every((item) => typeof item === 'string');
  const isNullableString = (v: unknown): v is string | null => v === null || typeof v === 'string';

  return {
    trigger: typeof obj.trigger === 'string' ? obj.trigger : undefined,
    task: typeof obj.task === 'string' ? obj.task : undefined,
    blocked_reasons: isStringArray(obj.blocked_reasons) ? obj.blocked_reasons : undefined,
    changed_fields:
      obj.changed_fields && typeof obj.changed_fields === 'object'
        ? (obj.changed_fields as Record<string, unknown>)
        : undefined,
    previous_assignee_id: isNullableString(obj.previous_assignee_id) ? obj.previous_assignee_id : undefined,
    new_assignee_id: isNullableString(obj.new_assignee_id) ? obj.new_assignee_id : undefined,
    action_kind: typeof obj.action_kind === 'string' ? obj.action_kind : undefined,
    action_display_name: typeof obj.action_display_name === 'string' ? obj.action_display_name : undefined,
    error: typeof obj.error === 'string' ? obj.error : undefined,
    message: typeof obj.message === 'string' ? obj.message : undefined,
    refused: typeof obj.refused === 'boolean' ? obj.refused : undefined,
    trigger_source: typeof obj.trigger_source === 'string' ? obj.trigger_source : undefined,
    triggered_by: typeof obj.triggered_by === 'string' ? obj.triggered_by : undefined,
    action_index: typeof obj.action_index === 'number' ? obj.action_index : undefined,
    action_total: typeof obj.action_total === 'number' ? obj.action_total : undefined,
    reason: typeof obj.reason === 'string' ? obj.reason : undefined,
    filled_fields: Array.isArray(obj.filled_fields)
      ? obj.filled_fields.filter((f): f is string => typeof f === 'string')
      : undefined,
    unresolved_sources: Array.isArray(obj.unresolved_sources)
      ? obj.unresolved_sources.filter((s): s is string => typeof s === 'string')
      : undefined,
  };
}

/** Maps one GET /audit-events row to a TimelineEvent. Returns null for event
 * types this timeline doesn't render (e.g. comments) — the row is still
 * counted toward pagination offset, just not displayed. */
function normalizeAuditEvent(item: AuditEventResponse): TimelineEvent | null {
  if (!item.event_timestamp) return null;

  const metadata = readEventMetadata(item.metadata);

  const base = {
    id: item.id,
    occurredAt: item.event_timestamp,
    actorName: item.actor_name,
    actorRole: item.actor_role,
  };

  switch (item.event_type) {
    case 'TRANSITION_SUCCEEDED':
      return { ...base, kind: 'transition_succeeded', fromState: item.before_state ?? undefined, toState: item.after_state ?? undefined, trigger: metadata.trigger };
    case 'TRANSITION_BLOCKED':
      return { ...base, kind: 'transition_blocked', fromState: item.before_state ?? undefined, toState: item.after_state ?? undefined, trigger: metadata.trigger, blockedReasons: metadata.blocked_reasons };
    case 'TRANSITION_CONFLICT':
      return { ...base, kind: 'transition_conflict', fromState: item.before_state ?? undefined, toState: item.after_state ?? undefined };
    case 'TASK_EXECUTED':
      return { ...base, kind: 'task_executed', trigger: metadata.task };
    case 'ENTITY_CREATED':
      return { ...base, kind: 'entity_created' };
    case 'ENTITY_UPDATED':
      return { ...base, kind: 'entity_updated', changedFieldCount: Object.keys(metadata.changed_fields ?? {}).length };
    case 'ENTITY_ASSIGNEE_CHANGED':
      return { ...base, kind: 'assignee_changed', previousAssigneeId: metadata.previous_assignee_id ?? null, newAssigneeId: metadata.new_assignee_id ?? null };
    case 'ENTITY_ARCHIVED':
      return { ...base, kind: 'entity_archived' };
    case 'ENTITY_RESTORED':
      return { ...base, kind: 'entity_restored' };
    case 'ACTION_STARTED':
      return { ...base, kind: 'action_started', actionKind: metadata.action_kind, actionDisplayName: metadata.action_display_name, triggerSource: metadata.trigger_source, triggeredById: metadata.triggered_by ?? null, actionIndex: metadata.action_index, actionTotal: metadata.action_total };
    case 'ACTION_COMPLETED':
      // A refused run completed successfully but changed nothing. `kind` is a
      // presentation choice only — it drives the icon, colour and headline. It
      // gets its own amber state rather than reusing `action_failed`, so a
      // business finding stays distinguishable from a crash. The run itself is
      // still `succeeded`: outcome routing and the failure policy are
      // unaffected.
      if (metadata.refused) {
        return { ...base, kind: 'action_refused', actionKind: metadata.action_kind, actionDisplayName: metadata.action_display_name, outcomeMessage: metadata.message, actionIndex: metadata.action_index, actionTotal: metadata.action_total };
      }
      return { ...base, kind: 'action_completed', actionKind: metadata.action_kind, actionDisplayName: metadata.action_display_name, outcomeMessage: metadata.message, actionIndex: metadata.action_index, actionTotal: metadata.action_total };
    case 'ACTION_FAILED':
    case 'ACTION_ALERT':
      return { ...base, kind: 'action_failed', actionKind: metadata.action_kind, actionDisplayName: metadata.action_display_name, errorMessage: metadata.error, actionIndex: metadata.action_index, actionTotal: metadata.action_total };
    case 'ACTION_RETRY_SCHEDULED':
      return { ...base, kind: 'action_retry_scheduled', actionKind: metadata.action_kind, actionDisplayName: metadata.action_display_name, errorMessage: metadata.error, actionIndex: metadata.action_index, actionTotal: metadata.action_total };
    case 'ACTION_WAITING_EXTERNAL':
      return { ...base, kind: 'action_waiting_external', actionKind: metadata.action_kind, actionDisplayName: metadata.action_display_name, actionIndex: metadata.action_index, actionTotal: metadata.action_total };
    case 'ACTION_CHAIN_SKIPPED':
      return { ...base, kind: 'action_chain_skipped', actionKind: metadata.action_kind, chainReason: metadata.reason };
    case 'ACTION_CHAIN_STOPPED':
      return { ...base, kind: 'action_chain_stopped', actionKind: metadata.action_kind, chainReason: metadata.reason };
    default:
      return null;
  }
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export interface UseActivityTimelineReturn {
  timeline: TimelineEvent[];
  isLoading: boolean;
  isError: boolean;
  hasMore: boolean;
  isFetchingMore: boolean;
  fetchMore: () => void;
  refetch: () => void;
}

/** Entity CRUD, transitions, and workflow lifecycle events in one chronological
 * feed, sourced from the single unified audit log endpoint, newest-first. */
export function useActivityTimeline(entityId: string): UseActivityTimelineReturn {
  const query = useInfiniteQuery({
    queryKey: timelineKeys.all(entityId),
    queryFn: ({ pageParam }) =>
      eventsApi.listActivity(entityId, { limit: PAGE_SIZE, offset: pageParam as number }),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      const fetched = allPages.flatMap((p) => p.items).length;
      return fetched < lastPage.total ? fetched : undefined;
    },
  });

  const timeline = (query.data?.pages ?? [])
    .flatMap((p) => p.items)
    .map(normalizeAuditEvent)
    .filter((e): e is TimelineEvent => e !== null);

  return {
    timeline,
    isLoading: query.isLoading,
    isError: query.isError,
    hasMore: query.hasNextPage ?? false,
    isFetchingMore: query.isFetchingNextPage,
    fetchMore: () => {
      if (query.hasNextPage && !query.isFetchingNextPage) void query.fetchNextPage();
    },
    refetch: () => void query.refetch(),
  };
}
