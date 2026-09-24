/**
 * DashboardGauge Component
 *
 * Presentational radial gauge for bounded-ratio widgets (e.g. SLA compliance).
 * Renders a single-value arc with the percentage in the center. No data fetching.
 */

import { useMemo } from 'react';
import { PolarAngleAxis, RadialBar, RadialBarChart, ResponsiveContainer } from 'recharts';

interface DashboardGaugeProps {
  value: number;
  max: number;
  label?: string;
}

function gaugeColor(pct: number): string {
  if (pct >= 80) return 'var(--color-chart-6)'; // emerald
  if (pct >= 50) return 'var(--color-chart-4)'; // amber
  return 'var(--color-chart-7)'; // red
}

export default function DashboardGauge({ value, max, label }: DashboardGaugeProps) {
  const pct = useMemo(() => (max > 0 ? Math.max(0, Math.min(value, max)) : 0), [value, max]);
  const data = [{ name: label ?? 'value', value: pct, fill: gaugeColor((pct / max) * 100) }];

  return (
    <div className="relative flex h-full w-full items-center justify-center">
      <ResponsiveContainer width="100%" height="100%">
        <RadialBarChart
          data={data}
          startAngle={210}
          endAngle={-30}
          innerRadius="70%"
          outerRadius="100%"
        >
          <PolarAngleAxis type="number" domain={[0, max]} tick={false} axisLine={false} />
          <RadialBar dataKey="value" cornerRadius={8} background animationDuration={600} />
        </RadialBarChart>
      </ResponsiveContainer>
      <div className="pointer-events-none absolute flex flex-col items-center">
        <span className="text-2xl font-semibold tabular-nums text-foreground">
          {value.toLocaleString(undefined, { maximumFractionDigits: 1 })}
          {max === 100 ? '%' : ''}
        </span>
        {label && <span className="text-xs text-muted-foreground">{label}</span>}
      </div>
    </div>
  );
}

export type { DashboardGaugeProps };
