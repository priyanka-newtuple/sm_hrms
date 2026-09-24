import { MousePointerClick } from 'lucide-react';

import { Card, DashboardChart } from '@/core/components';
import type { ActionBreakdownResponse } from '@/core/services/api/analytics';
import { humanize } from './lib';

type Props = {
  actions: ActionBreakdownResponse;
};

export function ActionBreakdownCard({ actions }: Props) {
  const series = actions.items.map((item) => ({
    label: humanize(item.action),
    value: item.count,
  }));

  return (
    <Card>
      <div className="mb-4 flex items-center gap-2">
        <MousePointerClick className="h-4 w-4 text-cobalt" />
        <h2 className="font-semibold">Action breakdown</h2>
      </div>
      <div className="h-80">
        <DashboardChart viz="bar" series={series} xLabel="Action" yLabel="Count" />
      </div>
    </Card>
  );
}
