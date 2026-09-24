import { Card, DashboardStat } from '@/core/components';
import type { ActionBreakdownResponse, LoginActivityResponse } from '@/core/services/api/analytics';

type Props = {
  logins: LoginActivityResponse;
  actions: ActionBreakdownResponse;
};

export function AnalyticsSummary({ logins, actions }: Props) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <Card className="min-h-36">
        <p className="mb-3 text-sm font-medium text-muted-foreground">Active users</p>
        <DashboardStat value={logins.active_users} icon="users" subtitle="People who logged in" />
      </Card>
      <Card className="min-h-36">
        <p className="mb-3 text-sm font-medium text-muted-foreground">Successful logins</p>
        <DashboardStat value={logins.total_logins} icon="zap" />
      </Card>
      <Card className="min-h-36">
        <p className="mb-3 text-sm font-medium text-muted-foreground">Total actions</p>
        <DashboardStat value={actions.total_actions} icon="chart-bar" subtitle="Authentication excluded" />
      </Card>
    </div>
  );
}
