import { useState } from 'react';
import type { ColumnDef, Row } from '@tanstack/react-table';
import { ChevronDown } from 'lucide-react';

import { Card } from '@/core/components';
import { DataTable, NumberCell } from '@/core/components/DataTable';
import { usePermissions } from '@/core/hooks/usePermissions';
import type { AnalyticsDateParams, UserActivityResponse } from '@/core/services/api/analytics';
import { formatTableCell } from '@/core/utils';
import { humanize } from './lib';
import { PaginationControls } from './PaginationControls';
import { UserActionDetails } from './UserActionDetails';

type UserActivityItem = UserActivityResponse['items'][number];

type Props = {
  users: UserActivityResponse;
  dateParams: AnalyticsDateParams;
  isFetching: boolean;
  onOffsetChange: (offset: number) => void;
};

function displayNameOf(user: UserActivityItem): string {
  return user.actor_type === 'system' ? 'System' : user.name;
}

type ActionGridButtonProps = {
  action: UserActivityItem['actions'][number];
  isSelected: boolean;
  canViewActionDetails: boolean;
  onSelect: () => void;
};

/** One tile in the action-breakdown grid; toggles the drill-down for that action. */
function ActionGridButton({
  action,
  isSelected,
  canViewActionDetails,
  onSelect,
}: ActionGridButtonProps) {
  return (
    <button
      type="button"
      disabled={!canViewActionDetails}
      onClick={onSelect}
      className={`flex items-center justify-between gap-3 rounded-lg border bg-background px-3 py-2.5 text-left transition-colors ${
        isSelected
          ? 'border-cobalt/50 bg-cobalt/5'
          : 'border-border hover:border-cobalt/30 hover:bg-cobalt/5'
      } disabled:cursor-default disabled:hover:border-border disabled:hover:bg-background`}
    >
      <div className="min-w-0">
        <p className="break-words font-medium text-foreground">{humanize(action.action)}</p>
        <p className="mt-0.5 text-xs capitalize text-muted-foreground">
          {canViewActionDetails
            ? `${humanize(action.category)} · ${isSelected ? 'Hide records' : 'View records'}`
            : humanize(action.category)}
        </p>
      </div>
      <span className="shrink-0 rounded-full bg-cobalt/10 px-2.5 py-1 font-mono text-xs font-semibold tabular-nums text-cobalt">
        {action.count.toLocaleString()}
      </span>
    </button>
  );
}

/**
 * Expanded content for one user: the per-action grid plus the drill-down for a
 * selected action. Mounted only while its row is expanded, so the selection
 * resets when the row is collapsed.
 */
function UserActionBreakdownPanel({
  user,
  dateParams,
  canViewActionDetails,
}: {
  user: UserActivityItem;
  dateParams: AnalyticsDateParams;
  canViewActionDetails: boolean;
}) {
  const [selectedActionKey, setSelectedActionKey] = useState<string | null>(null);
  const displayName = displayNameOf(user);
  const selectedAction = user.actions.find(
    (action) => `${action.category}:${action.action}` === selectedActionKey,
  );

  return (
    <div className="px-4 py-4">
      <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Actions performed by {displayName}
      </p>
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {user.actions.map((action) => {
          const actionKey = `${action.category}:${action.action}`;
          const isSelected = actionKey === selectedActionKey;
          return (
            <ActionGridButton
              key={actionKey}
              action={action}
              isSelected={isSelected}
              canViewActionDetails={canViewActionDetails}
              onSelect={() => setSelectedActionKey(isSelected ? null : actionKey)}
            />
          );
        })}
      </div>
      {!canViewActionDetails && (
        <p className="mt-3 text-xs text-muted-foreground">
          Individual records require entity record read permission.
        </p>
      )}
      {selectedAction && (
        <UserActionDetails
          key={`${user.user_id}:${selectedActionKey}`}
          userId={user.user_id}
          userName={displayName}
          action={selectedAction.action}
          dateParams={dateParams}
        />
      )}
    </div>
  );
}

/** "View N action types" / "Hide actions" toggle, or a plain label when there's nothing to expand. */
function BreakdownToggleCell({ row }: { row: Row<UserActivityItem> }) {
  const actionTypeCount = row.original.actions.length;
  if (actionTypeCount === 0) {
    return <span className="text-xs text-muted-foreground">No actions</span>;
  }
  const isExpanded = row.getIsExpanded();
  return (
    <button
      type="button"
      aria-expanded={isExpanded}
      onClick={() => row.toggleExpanded()}
      className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:border-cobalt/40 hover:bg-cobalt/5 hover:text-cobalt"
    >
      {isExpanded
        ? 'Hide actions'
        : `View ${actionTypeCount} action ${actionTypeCount === 1 ? 'type' : 'types'}`}
      <ChevronDown className={`size-3.5 transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
    </button>
  );
}

/** Per-user login and action activity, expandable to a breakdown and record drill-down. */
export function UserActivityTable({ users, dateParams, isFetching, onOffsetChange }: Props) {
  const { hasPermission } = usePermissions();
  const canViewActionDetails = hasPermission('entity_record:read');

  const columns: ColumnDef<UserActivityItem, unknown>[] = [
    {
      id: 'person',
      header: 'Person',
      cell: ({ row }) => (
        <div>
          <p className="font-medium text-foreground">{displayNameOf(row.original)}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {row.original.actor_type === 'system'
              ? 'Automated activity'
              : (row.original.email ?? `User ID: ${row.original.user_id}`)}
          </p>
        </div>
      ),
    },
    {
      id: 'last_login',
      header: 'Last login',
      cell: ({ row }) => (
        <span className="whitespace-nowrap text-foreground">
          {formatTableCell(row.original.last_login_at)}
        </span>
      ),
    },
    {
      id: 'logins',
      header: 'Logins',
      cell: ({ row }) => <NumberCell value={row.original.login_count} />,
      meta: { numeric: true, width: '7rem' },
    },
    {
      id: 'total_actions',
      header: 'Total actions',
      cell: ({ row }) => <NumberCell value={row.original.total_actions} />,
      meta: { numeric: true, width: '9rem' },
    },
    {
      id: 'breakdown',
      header: 'Breakdown',
      cell: ({ row }) => <BreakdownToggleCell row={row} />,
      meta: { align: 'right', width: '12rem' },
    },
  ];

  return (
    <Card>
      <div className="mb-4">
        <h2 className="font-semibold">Per-user activity</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Successful logins and attributable actions in this period. Expand a person to see what they
          did.
        </p>
      </div>
      <div className="min-h-48 overflow-hidden rounded-lg border border-border">
        <DataTable
          label="Per-user activity"
          data={users.items}
          columns={columns}
          getRowId={(user) => user.user_id}
          enableSorting={false}
          renderExpanded={(user) => (
            <UserActionBreakdownPanel
              user={user}
              dateParams={dateParams}
              canViewActionDetails={canViewActionDetails}
            />
          )}
          getRowCanExpand={(user) => user.actions.length > 0}
          framed={false}
          emptyState={
            <div className="flex min-h-48 items-center justify-center text-sm text-muted-foreground">
              No attributable user activity
            </div>
          }
        />
      </div>
      <PaginationControls
        total={users.total}
        limit={users.limit}
        offset={users.offset}
        isFetching={isFetching}
        onOffsetChange={onOffsetChange}
      />
    </Card>
  );
}
