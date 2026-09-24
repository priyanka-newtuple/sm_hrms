import type { DateRange } from 'react-day-picker';
import { CalendarDays } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { DatePickerWithRange } from '@/components/ui/range-picker';
import { EmptyState, SkeletonPage } from '@/core/components';
import { getApiErrorMessage } from '@/core/services/api/client';
import type {
  AnalyticsDateParams,
  ActionBreakdownResponse,
  LoginActivityResponse,
  UserActivityResponse,
} from '@/core/services/api/analytics';
import { ActionBreakdownCard } from './ActionBreakdownCard';
import { AnalyticsSummary } from './AnalyticsSummary';
import { FlexibleReportCard } from './FlexibleReportCard';
import { LoginActivityCard } from './LoginActivityCard';
import { UserActivityTable } from './UserActivityTable';
import { useAnalyticsDateRange, useAnalyticsReports } from './hooks/useAnalytics';

type HeaderProps = {
  range: DateRange | undefined;
  onRangeChange: (range: DateRange | undefined) => void;
  onResetToLast30Days: () => void;
};

/** Title, description, and date-range controls shown above every state (loading/error/success). */
function AnalyticsPageHeader({ range, onRangeChange, onResetToLast30Days }: HeaderProps) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">User analytics</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Login and action activity for your organization, reported in UTC.
        </p>
      </div>
      <div className="flex items-center gap-2">
        <DatePickerWithRange value={range} onChange={onRangeChange} />
        <Button variant="outline" size="sm" onClick={onResetToLast30Days}>
          Last 30 days
        </Button>
      </div>
    </div>
  );
}

type ReportsContentProps = {
  logins: LoginActivityResponse;
  actions: ActionBreakdownResponse;
  users: UserActivityResponse;
  dateParams: AnalyticsDateParams;
  isFetching: boolean;
  onUserOffsetChange: (offset: number) => void;
};

/** Renders the loaded reports, or an empty state if the range has no activity. */
function AnalyticsReportsContent({
  logins,
  actions,
  users,
  dateParams,
  isFetching,
  onUserOffsetChange,
}: ReportsContentProps) {
  const hasActivity = logins.total_logins > 0 || actions.total_actions > 0;

  if (!hasActivity) {
    return (
      <EmptyState
        surface="panel"
        icon={<CalendarDays className="h-8 w-8" />}
        title="Nothing here yet"
        description="There were no logins or actions in the selected date range."
      />
    );
  }

  return (
    <>
      <AnalyticsSummary logins={logins} actions={actions} />
      <div className="grid gap-6 xl:grid-cols-2">
        <LoginActivityCard logins={logins} />
        <ActionBreakdownCard actions={actions} />
      </div>
      <UserActivityTable
        users={users}
        dateParams={dateParams}
        isFetching={isFetching}
        onOffsetChange={onUserOffsetChange}
      />
      <FlexibleReportCard
        key={`${dateParams.date_from ?? ''}:${dateParams.date_to ?? ''}`}
        dateParams={dateParams}
      />
    </>
  );
}

/** Settings tab showing org-wide login and action analytics for a selected date range. */
export default function AnalyticsTab() {
  const { range, dateParams, userOffset, setUserOffset, setRange, resetToLast30Days } =
    useAnalyticsDateRange();
  const reports = useAnalyticsReports(dateParams, 25, userOffset);

  const header = (
    <AnalyticsPageHeader
      range={range}
      onRangeChange={setRange}
      onResetToLast30Days={resetToLast30Days}
    />
  );

  if (reports.isPending) {
    return (
      <div className="mx-auto max-w-7xl space-y-6">
        {header}
        <SkeletonPage />
      </div>
    );
  }

  if (reports.error) {
    return (
      <div className="mx-auto max-w-7xl space-y-6">
        {header}
        <EmptyState
          surface="panel"
          title="Analytics could not be loaded"
          description={getApiErrorMessage(reports.error, 'Try again in a moment.')}
          action={<Button onClick={() => void reports.refetch()}>Try again</Button>}
        />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      {header}
      <AnalyticsReportsContent
        {...reports.data}
        dateParams={dateParams}
        isFetching={reports.isFetching}
        onUserOffsetChange={setUserOffset}
      />
    </div>
  );
}
