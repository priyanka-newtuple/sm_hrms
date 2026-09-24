import { useMemo, useState } from 'react';
import { format, subDays } from 'date-fns';
import type { DateRange } from 'react-day-picker';
import { keepPreviousData, useQuery } from '@tanstack/react-query';

import {
  analytics,
  type AnalyticsDateParams,
  type AnalyticsGroupBy,
} from '@/core/services/api/analytics';
import { events } from '@/core/services/api/events';

const DEFAULT_RANGE_DAYS = 29;

/** Own the date-range picker state and derive the `date_from`/`date_to` query params from it. */
export function useAnalyticsDateRange() {
  const today = useMemo(() => new Date(), []);
  const [range, setRange] = useState<DateRange | undefined>({
    from: subDays(today, DEFAULT_RANGE_DAYS),
    to: today,
  });
  const [userOffset, setUserOffset] = useState(0);

  const dateParams: AnalyticsDateParams = {
    ...(range?.from ? { date_from: format(range.from, 'yyyy-MM-dd') } : {}),
    ...(range?.to ? { date_to: format(range.to, 'yyyy-MM-dd') } : {}),
  };

  const setRangeAndResetPage = (nextRange: DateRange | undefined) => {
    setRange(nextRange);
    setUserOffset(0);
  };

  const resetToLast30Days = () => setRangeAndResetPage({ from: subDays(today, DEFAULT_RANGE_DAYS), to: today });

  return { range, dateParams, userOffset, setUserOffset, setRange: setRangeAndResetPage, resetToLast30Days };
}

/** Fetch all fixed reports in one request and keep the previous page visible. */
export function useAnalyticsReports(
  params: AnalyticsDateParams,
  userLimit: number,
  userOffset: number,
) {
  return useQuery({
    queryKey: ['analytics', 'overview', params.date_from, params.date_to, userLimit, userOffset],
    queryFn: () => analytics.overview({
      ...params,
      user_limit: userLimit,
      user_offset: userOffset,
    }),
    placeholderData: keepPreviousData,
  });
}

/** Fetch the flexible grouped report for the current dimensions. */
export function useFlexibleReport(
  params: AnalyticsDateParams,
  groupBy: AnalyticsGroupBy[],
  includeAuth: boolean,
  limit: number,
  offset: number,
) {
  return useQuery({
    queryKey: [
      'analytics',
      'flexible',
      params.date_from,
      params.date_to,
      groupBy.join('+'),
      includeAuth,
      limit,
      offset,
    ],
    queryFn: () => analytics.flexible({
      ...params,
      group_by: groupBy,
      include_auth: includeAuth,
      limit,
      offset,
    }),
    placeholderData: keepPreviousData,
  });
}

/** Fetch one page of individual audit records behind an action count. */
export function useUserActionDetails(
  params: AnalyticsDateParams,
  userId: string,
  eventType: string,
  limit: number,
  offset: number,
) {
  return useQuery({
    queryKey: [
      'analytics',
      'action-details',
      params.date_from,
      params.date_to,
      userId,
      eventType,
      limit,
      offset,
    ],
    queryFn: () => events.listUserActionActivity({
      ...params,
      user_id: userId,
      event_type: eventType,
      limit,
      offset,
    }),
    placeholderData: keepPreviousData,
  });
}
