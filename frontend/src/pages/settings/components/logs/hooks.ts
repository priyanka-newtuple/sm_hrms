import { useCallback, useState } from 'react';
import type { DateRange } from 'react-day-picker';

import { useApi } from '@/core/hooks/useApi';
import { users as usersApi } from '@/core/services/api';
import type { User } from '@/core/types';
import { useEntityRecordLink } from '@/shared/hooks/useEntityRecordLink';
import type { FieldChangeRow } from './lib';

/** Filter and paging state. Changing a filter resets to the first page. */
export function useLogsFilters() {
  const [range, setRange] = useState<DateRange | undefined>();
  const [userId, setUserId] = useState<string | null>(null);
  const [page, setPage] = useState(0);

  const onRangeChange = useCallback((next: DateRange | undefined) => {
    setRange(next);
    setPage(0);
  }, []);

  const onPersonChange = useCallback((next: string | null) => {
    setUserId(next);
    setPage(0);
  }, []);

  return { range, userId, page, setPage, onRangeChange, onPersonChange };
}

/** Org users, plus a resolver turning an assignee id into a display name. */
export function useOrgUsers(): { users: User[]; resolveUserName: (id: unknown) => string } {
  const fetchUsers = useCallback(() => usersApi.list(), []);
  const { data } = useApi(fetchUsers, { immediate: true });

  const resolveUserName = useCallback(
    (id: unknown) => {
      if (!id || typeof id !== 'string') return 'Unassigned';
      return (data ?? []).find((user) => user.id === id)?.full_name ?? id;
    },
    [data],
  );

  return { users: data ?? [], resolveUserName };
}

/** Logs-page adapter over the shared record deep-link. */
export function useRecordLink() {
  const { isLinkable, openRecord } = useEntityRecordLink('/settings?tab=logs');
  return {
    isRecordLinkable: (row: FieldChangeRow) =>
      !row.entityArchived && isLinkable(row.entityType, row.entityId),
    openRecord: (row: FieldChangeRow) => openRecord(row.entityType, row.entityId),
  };
}
