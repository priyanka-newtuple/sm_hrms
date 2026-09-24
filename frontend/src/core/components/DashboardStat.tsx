/**
 * DashboardStat Component
 *
 * Presentational KPI card body for dashboard "scalar" widgets. Shows the value
 * with locale formatting, an optional accent icon, and a trend delta versus the
 * previous period (direction arrow + percentage, colored up/down/flat). No data
 * fetching or business logic.
 */

import { useMemo } from 'react';
import { Minus, TrendingDown, TrendingUp } from 'lucide-react';
import { cn } from '../../lib/utils';
import { percentChange } from '../utils';
import { getWidgetIcon } from './widgetIcons';

interface DashboardStatProps {
  value: number;
  prevValue?: number;
  /** Optional Lucide icon name shown in the accent badge. */
  icon?: string;
  subtitle?: string;
}

export default function DashboardStat({ value, prevValue, icon, subtitle }: DashboardStatProps) {
  const Icon = getWidgetIcon(icon);
  const delta = useMemo(() => percentChange(value, prevValue), [value, prevValue]);

  const direction: 'up' | 'down' | 'flat' | null =
    delta == null ? null : delta > 0.05 ? 'up' : delta < -0.05 ? 'down' : 'flat';

  const TrendIcon = direction === 'up' ? TrendingUp : direction === 'down' ? TrendingDown : Minus;
  const trendClass =
    direction === 'up'
      ? 'bg-emerald-500/10 text-emerald-600'
      : direction === 'down'
        ? 'bg-rose-500/10 text-rose-600'
        : 'bg-muted text-muted-foreground';

  return (
    <div className="flex h-full flex-col justify-center gap-2">
      <div className="flex items-start justify-between gap-2">
        <span className="text-3xl font-semibold tabular-nums text-foreground">
          {value.toLocaleString()}
        </span>
        {Icon && (
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-cobalt/10 text-cobalt">
            <Icon className="h-5 w-5" strokeWidth={1.5} />
          </span>
        )}
      </div>
      {subtitle && (
        <span className="text-xs text-muted-foreground">
          {subtitle.replace('{value}', value.toLocaleString())}
        </span>
      )}
      {direction && (
        <div className="flex items-center gap-2 text-xs">
          <span
            className={cn(
              'inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 font-medium tabular-nums',
              trendClass,
            )}
          >
            <TrendIcon className="h-3 w-3" strokeWidth={2} />
            {delta != null && `${delta > 0 ? '+' : ''}${delta.toFixed(1)}%`}
          </span>
          {typeof prevValue === 'number' && (
            <span className="text-muted-foreground">vs {prevValue.toLocaleString()} prev</span>
          )}
        </div>
      )}
    </div>
  );
}

export type { DashboardStatProps };
