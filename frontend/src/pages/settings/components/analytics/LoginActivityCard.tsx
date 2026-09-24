import { useState } from 'react';
import { Users } from 'lucide-react';

import { Card, DashboardChart } from '@/core/components';
import type { LoginActivityResponse } from '@/core/services/api/analytics';

type Bucket = 'daily' | 'weekly';

type Props = {
  logins: LoginActivityResponse;
};

export function LoginActivityCard({ logins }: Props) {
  const [bucket, setBucket] = useState<Bucket>('daily');

  return (
    <Card>
      <div className="mb-4 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Users className="h-4 w-4 text-cobalt" />
          <h2 className="font-semibold">Login activity</h2>
        </div>
        <div className="flex rounded-md border border-border p-0.5">
          {(['daily', 'weekly'] as const).map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={bucket === option}
              onClick={() => setBucket(option)}
              className={`rounded px-2 py-1 text-xs capitalize ${
                bucket === option
                  ? 'bg-cobalt/10 font-medium text-cobalt'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {option}
            </button>
          ))}
        </div>
      </div>
      <div className="h-80">
        <DashboardChart
          viz="line"
          series={bucket === 'daily' ? logins.daily : logins.weekly}
          xLabel={bucket === 'daily' ? 'Day (UTC)' : 'Week (UTC)'}
          yLabel="Logins"
        />
      </div>
    </Card>
  );
}
