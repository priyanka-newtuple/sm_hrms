import { useState } from 'react';
import { BarChart3 } from 'lucide-react';

import { Card, DashboardTable } from '@/core/components';
import { getApiErrorMessage } from '@/core/services/api/client';
import type {
  AnalyticsDateParams,
  AnalyticsGroupBy,
  FlexibleAnalyticsResponse,
} from '@/core/services/api/analytics';
import { useFlexibleReport } from './hooks/useAnalytics';
import { GROUP_OPTIONS, humanize } from './lib';
import { PaginationControls } from './PaginationControls';

const NO_SECONDARY = 'none';

const SELECT_STYLES = 'h-9 rounded-md border border-border bg-background px-3 text-sm text-foreground';

type Props = {
  dateParams: AnalyticsDateParams;
};

type FiltersProps = {
  primaryGroup: AnalyticsGroupBy;
  secondaryGroup: string;
  includeAuth: boolean;
  onPrimaryGroupChange: (group: AnalyticsGroupBy) => void;
  onSecondaryGroupChange: (group: string) => void;
  onIncludeAuthChange: (includeAuth: boolean) => void;
};

/** Group-by dimension selects and the include-authentication checkbox. */
function FlexibleReportFilters({
  primaryGroup,
  secondaryGroup,
  includeAuth,
  onPrimaryGroupChange,
  onSecondaryGroupChange,
  onIncludeAuthChange,
}: FiltersProps) {
  return (
    <div className="flex flex-wrap items-end gap-3">
      <label className="grid gap-1 text-xs font-medium text-muted-foreground">
        Group by
        <select
          className={SELECT_STYLES}
          value={primaryGroup}
          onChange={(event) => onPrimaryGroupChange(event.target.value as AnalyticsGroupBy)}
        >
          {GROUP_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      </label>
      <label className="grid gap-1 text-xs font-medium text-muted-foreground">
        Then by
        <select
          className={SELECT_STYLES}
          value={secondaryGroup}
          onChange={(event) => onSecondaryGroupChange(event.target.value)}
        >
          <option value={NO_SECONDARY}>Nothing</option>
          {GROUP_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      </label>
      <label className="flex h-9 items-center gap-2 text-sm text-muted-foreground">
        <input
          type="checkbox"
          checked={includeAuth}
          onChange={(event) => onIncludeAuthChange(event.target.checked)}
        />
        Include authentication
      </label>
    </div>
  );
}

type ContentProps = {
  isPending: boolean;
  error: unknown;
  data: FlexibleAnalyticsResponse | undefined;
  isFetching: boolean;
  onOffsetChange: (offset: number) => void;
};

/** Loading/error/table+pagination states for the flexible report's fetched data. */
function FlexibleReportContent({ isPending, error, data, isFetching, onOffsetChange }: ContentProps) {
  if (isPending) {
    return <div className="py-12 text-center text-sm text-muted-foreground">Loading flexible report…</div>;
  }

  if (error) {
    return (
      <div className="py-12 text-center text-sm text-muted-foreground">
        {getApiErrorMessage(error, 'The flexible report could not be loaded.')}
      </div>
    );
  }

  const displayRows = (data?.rows ?? []).map((row) => ({
    ...row,
    ...(typeof row.action === 'string' ? { action: humanize(row.action) } : {}),
    ...(typeof row.category === 'string' ? { category: humanize(row.category) } : {}),
  }));

  return (
    <div className="space-y-3">
      <DashboardTable columns={data?.columns ?? []} rows={displayRows} />
      {data && (
        <PaginationControls
          total={data.total}
          limit={data.limit}
          offset={data.offset}
          isFetching={isFetching}
          onOffsetChange={onOffsetChange}
        />
      )}
    </div>
  );
}

/** Setter wrapper so changing any filter also resets pagination back to page one. */
function withPageReset<T>(setter: (value: T) => void, resetOffset: () => void) {
  return (value: T) => {
    setter(value);
    resetOffset();
  };
}

const CARD_TITLE = (
  <div>
    <div className="flex items-center gap-2">
      <BarChart3 className="h-4 w-4 text-cobalt" />
      <h2 className="font-semibold">Flexible view</h2>
    </div>
    <p className="mt-1 text-sm text-muted-foreground">Group usage counts by up to two dimensions.</p>
  </div>
);

/** Custom report card: group usage counts by up to two user-selected dimensions. */
export function FlexibleReportCard({ dateParams }: Props) {
  const pageSize = 50;
  const [primaryGroup, setPrimaryGroup] = useState<AnalyticsGroupBy>('day');
  const [secondaryGroup, setSecondaryGroup] = useState<string>('action');
  const [includeAuth, setIncludeAuth] = useState(false);
  const [offset, setOffset] = useState(0);
  const resetOffset = () => setOffset(0);

  const groupBy: AnalyticsGroupBy[] = [
    primaryGroup,
    ...(secondaryGroup !== NO_SECONDARY && secondaryGroup !== primaryGroup
      ? [secondaryGroup as AnalyticsGroupBy]
      : []),
  ];
  const flexible = useFlexibleReport(dateParams, groupBy, includeAuth, pageSize, offset);

  return (
    <Card>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
        {CARD_TITLE}
        <FlexibleReportFilters
          primaryGroup={primaryGroup}
          secondaryGroup={secondaryGroup}
          includeAuth={includeAuth}
          onPrimaryGroupChange={withPageReset(setPrimaryGroup, resetOffset)}
          onSecondaryGroupChange={withPageReset(setSecondaryGroup, resetOffset)}
          onIncludeAuthChange={withPageReset(setIncludeAuth, resetOffset)}
        />
      </div>
      <div className="min-h-48">
        <FlexibleReportContent
          isPending={flexible.isPending}
          error={flexible.error}
          data={flexible.data}
          isFetching={flexible.isFetching}
          onOffsetChange={setOffset}
        />
      </div>
    </Card>
  );
}
