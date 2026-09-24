import { useMemo } from 'react';

import { useFieldChangeLogs } from '@/core/hooks/useFieldChangeLogs';
import FieldChangeTable from './FieldChangeTable';
import LogsFilterBar from './LogsFilterBar';
import { useLogsFilters, useOrgUsers, useRecordLink } from './hooks';
import { toDateParam, toFieldChangeRows } from './lib';

const PAGE_SIZE = 50;

/**
 * Settings → Govern → Logs: who changed what, on any record, across the org.
 *
 * Reads change history from `useFieldChangeLogs`, org users (to name
 * assignees) and entity types / state machines (to link rows back to a
 * record's Activity tab).
 */
export default function LogsTab() {
  const { range, userId, page, setPage, onRangeChange, onPersonChange } = useLogsFilters();
  const { users, resolveUserName } = useOrgUsers();
  const { isRecordLinkable, openRecord } = useRecordLink();

  const { data, loading, error } = useFieldChangeLogs({
    userId: userId ?? undefined,
    dateFrom: range?.from ? toDateParam(range.from) : undefined,
    dateTo: range?.to ? toDateParam(range.to) : undefined,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  });

  const rows = useMemo(() => toFieldChangeRows(data?.items ?? []), [data]);

  return (
    <div className="space-y-4 p-6">
      <div>
        <h2 className="text-lg font-semibold">Logs</h2>
        <p className="text-sm text-muted-foreground">
          Field changes across every record in your organization.
        </p>
      </div>

      <LogsFilterBar
        users={users}
        range={range}
        userId={userId}
        onRangeChange={onRangeChange}
        onPersonChange={onPersonChange}
      />

      {error ? (
        <p className="py-8 text-sm text-destructive">Unable to load field changes.</p>
      ) : (
        <FieldChangeTable
          rows={rows}
          isLoading={loading}
          onOpenRecord={openRecord}
          isRecordLinkable={isRecordLinkable}
          resolveUserName={resolveUserName}
          pagination={{
            // Events, not rows — one edit can touch several fields.
            total: data?.total ?? 0,
            limit: PAGE_SIZE,
            offset: page * PAGE_SIZE,
            onChange: (offset) => setPage(Math.floor(offset / PAGE_SIZE)),
          }}
        />
      )}
    </div>
  );
}
