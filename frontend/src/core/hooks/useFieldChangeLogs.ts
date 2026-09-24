/**
 * Field change logs hook
 *
 * Org-wide field change history for the Settings → Logs page, keeping the page
 * free of direct service imports (Component → Hook → Service).
 */

import { useCallback } from 'react';

import { events } from '../services/api';
import { useApi } from './useApi';

export type FieldChangeLogFilters = {
  userId?: string;
  dateFrom?: string;
  dateTo?: string;
  limit?: number;
  offset?: number;
};

/**
 * With no filters set this returns the most recent changes org-wide rather than
 * an empty state, so the page is useful before anyone touches a filter.
 */
export function useFieldChangeLogs({
  userId,
  dateFrom,
  dateTo,
  limit,
  offset,
}: FieldChangeLogFilters) {
  const fetcher = useCallback(
    () =>
      events.listFieldChanges({
        user_id: userId,
        date_from: dateFrom,
        date_to: dateTo,
        limit,
        offset,
      }),
    [userId, dateFrom, dateTo, limit, offset],
  );
  return useApi(fetcher, { immediate: true });
}
