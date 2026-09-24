import { useMemo, useState } from 'react';
import type { ColumnDef } from '@tanstack/react-table';

import { DataTable } from '@/core/components/DataTable';
import type { AnalyticsDateParams } from '@/core/services/api/analytics';
import type { AuditEventResponse } from '@/core/types';
import { formatTableCell } from '@/core/utils';
import { getApiErrorMessage } from '@/core/services/api/client';
import { useEntityRecordLink } from '@/shared/hooks/useEntityRecordLink';
import { useUserActionDetails } from './hooks/useAnalytics';
import { humanize } from './lib';
import { PaginationControls } from './PaginationControls';

type Props = {
  userId: string;
  userName: string;
  action: string;
  dateParams: AnalyticsDateParams;
};

const PAGE_SIZE = 10;
const MAX_DETAIL_FIELDS = 3;
const COMMENT_EVENT_PREFIXES = ['COMMENT_', 'REPLY_'] as const;
const ARCHIVED_COMMENT_EVENTS = new Set(['COMMENT_ARCHIVED', 'REPLY_ARCHIVED']);

type RecordLink = ReturnType<typeof useEntityRecordLink>;

function entityIdentifier(item: AuditEventResponse): string | null {
  if (item.entity_identifier?.trim()) return item.entity_identifier.trim();
  // Only ENTITY_CREATED payloads carry this — kept for rows predating
  // `entity_identifier` on the response.
  const recordedIdentifier = item.metadata?.identifier;
  return typeof recordedIdentifier === 'string' && recordedIdentifier.trim()
    ? recordedIdentifier.trim()
    : null;
}

type RecordsTableProps = {
  items: AuditEventResponse[];
  total: number;
  offset: number;
  isFetching: boolean;
  onOffsetChange: (offset: number) => void;
};

function isArchivedComment(item: AuditEventResponse): boolean {
  return ARCHIVED_COMMENT_EVENTS.has(item.event_type);
}

function openTarget(item: AuditEventResponse): { tab: 'activity' | 'comments'; commentId?: string } {
  const isCommentEvent = COMMENT_EVENT_PREFIXES.some((prefix) => item.event_type.startsWith(prefix));
  if (!isCommentEvent) return { tab: 'activity' };
  const commentId = item.metadata?.comment_id;
  return { tab: 'comments', commentId: typeof commentId === 'string' ? commentId : undefined };
}

type EntityCellProps = {
  item: AuditEventResponse;
  isLinkable: RecordLink['isLinkable'];
  openRecord: RecordLink['openRecord'];
};

function EntityCell({ item, isLinkable, openRecord }: EntityCellProps) {
  const label = entityIdentifier(item) ?? item.entity_type ?? 'Unknown entity';
  const canOpen = !item.entity_archived && !isArchivedComment(item) && isLinkable(item.entity_type, item.entity_id);

  return (
    <div className="max-w-[22rem]">
      {canOpen ? (
        <button
          type="button"
          onClick={() => openRecord(item.entity_type, item.entity_id, openTarget(item))}
          className="break-words text-left font-medium text-cobalt hover:underline"
        >
          {label}
        </button>
      ) : (
        <p className="break-words font-medium text-foreground">{label}</p>
      )}
      <p className="mt-0.5 text-xs text-muted-foreground">{item.entity_type ?? 'Entity'}</p>
    </div>
  );
}

/** What actually happened, per event type. Comment text is deliberately left
 *  out — it can be long, carry file URLs, and holds raw mention tokens. */
function eventDetail(item: AuditEventResponse): string | null {
  if (item.before_state || item.after_state) {
    return `${item.before_state ?? '—'} → ${item.after_state ?? '—'}`;
  }

  const changedFields = item.metadata?.changed_fields;
  if (changedFields && typeof changedFields === 'object') {
    const names = Object.keys(changedFields).map(humanize);
    if (names.length) {
      return names.length <= MAX_DETAIL_FIELDS
        ? names.join(', ')
        : `${names.slice(0, MAX_DETAIL_FIELDS).join(', ')} +${names.length - MAX_DETAIL_FIELDS} more`;
    }
  }

  if (item.metadata?.new_assignee_id || item.metadata?.previous_assignee_id) {
    return 'Assignee changed';
  }
  return null;
}

function buildColumns(link: RecordLink): ColumnDef<AuditEventResponse, unknown>[] {
  return [
  {
    id: 'entity',
    header: 'Entity',
    cell: ({ row }) => (
      <EntityCell item={row.original} isLinkable={link.isLinkable} openRecord={link.openRecord} />
    ),
  },
  {
    id: 'detail',
    header: 'Details',
    cell: ({ row }) => (
      <span className="line-clamp-2 text-muted-foreground">{eventDetail(row.original) ?? '—'}</span>
    ),
  },
  {
    id: 'performed_at',
    header: 'Performed at',
    cell: ({ row }) => (
      <span className="whitespace-nowrap text-muted-foreground">
        {formatTableCell(row.original.event_timestamp)}
      </span>
    ),
  },
  ];
}

/** Table + pagination for one page of audit records. Assumes `items` is non-empty. */
function RecordsTable({ items, total, offset, isFetching, onOffsetChange }: RecordsTableProps) {
  // Hoisted out of the cell: `useEntityTypes` inside it has no shared cache, so
  // one hook call per row meant one /entity-types request per row.
  const { isLinkable, openRecord } = useEntityRecordLink('/settings?tab=analytics');
  // The hook returns a fresh object each render; memoize on the stable callbacks.
  const columns = useMemo(
    () => buildColumns({ isLinkable, openRecord }),
    [isLinkable, openRecord],
  );

  return (
    <>
      <div className="overflow-hidden rounded-lg border border-border">
        <DataTable
          label="Activity records"
          data={items}
          columns={columns}
          getRowId={(item) => item.id}
          enableSorting={false}
          density="compact"
          // Nested inside an expanded row — let it size to its content rather
          // than creating a scroll region inside another scroll region.
          maxHeight="none"
          framed={false}
        />
      </div>
      <PaginationControls
        total={total}
        limit={PAGE_SIZE}
        offset={offset}
        isFetching={isFetching}
        onOffsetChange={onOffsetChange}
      />
    </>
  );
}

/** Show the individual audit records that make up one per-user action count. */
export function UserActionDetails({ userId, userName, action, dateParams }: Props) {
  const [offset, setOffset] = useState(0);
  const details = useUserActionDetails(dateParams, userId, action, PAGE_SIZE, offset);

  return (
    <div className="mt-4 rounded-lg border border-border bg-background p-4">
      <div className="mb-3">
        <h3 className="text-sm font-semibold text-foreground">{humanize(action)} records</h3>
        <p className="mt-0.5 text-xs text-muted-foreground">Performed by {userName}</p>
      </div>

      {details.isPending ? (
        <div className="py-6 text-center text-sm text-muted-foreground">Loading records…</div>
      ) : details.error ? (
        <div className="py-6 text-center text-sm text-muted-foreground">
          {getApiErrorMessage(details.error, 'The activity records could not be loaded.')}
        </div>
      ) : details.data.items.length === 0 ? (
        <div className="py-6 text-center text-sm text-muted-foreground">
          No matching records in this date range
        </div>
      ) : (
        <RecordsTable
          items={details.data.items}
          total={details.data.total}
          offset={offset}
          isFetching={details.isFetching}
          onOffsetChange={setOffset}
        />
      )}
    </div>
  );
}
