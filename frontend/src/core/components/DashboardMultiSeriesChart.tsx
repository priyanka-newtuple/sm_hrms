/**
 * DashboardMultiSeriesChart
 *
 * Presentational multi-line chart for "multiseries" widgets. One line per
 * series over a shared string x-axis, custom dot-legend (top-right), and a
 * tooltip that lists every series' value at the hovered x. No data fetching.
 */
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { CHART_PALETTE } from './DashboardChart';
import { formatCompactNumber } from '../utils';

interface SeriesDef {
  key: string;
  label: string;
  color?: string;
}
interface MultiPoint {
  label: string;
  [seriesKey: string]: number | string;
}
interface DashboardMultiSeriesChartProps {
  points: MultiPoint[];
  series: SeriesDef[];
}

const AXIS_TICK = { fontSize: 11, fill: 'var(--color-muted-foreground, #6b7280)' };
const GRID_STROKE = 'var(--color-border, #e5e7eb)';

interface TooltipProps {
  active?: boolean;
  label?: string | number;
  payload?: { name?: string; value?: number; color?: string }[];
}

function MultiTooltip({ active, label, payload }: TooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-border bg-background px-3 py-2 text-xs shadow-md">
      <div className="font-medium text-foreground">{label}</div>
      {payload.map((row) => (
        <div key={row.name} className="mt-0.5 flex items-center gap-1.5" style={{ color: row.color }}>
          <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: row.color }} />
          <span>{row.name} : </span>
          <span className="font-mono tabular-nums">{(row.value ?? 0).toLocaleString()}</span>
        </div>
      ))}
    </div>
  );
}

export default function DashboardMultiSeriesChart({ points, series }: DashboardMultiSeriesChartProps) {
  if (points.length === 0 || series.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        No data yet
      </div>
    );
  }
  return (
    <div className="flex h-full flex-col">
      <div className="mb-1 flex flex-wrap justify-end gap-3 text-[11px]">
        {series.map((s, i) => {
          const color = s.color ?? CHART_PALETTE[i % CHART_PALETTE.length];
          return (
            <span key={s.key} className="flex items-center gap-1 text-muted-foreground">
              <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
              {s.label}
            </span>
          );
        })}
      </div>
      <div className="min-h-0 flex-1">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
            <CartesianGrid strokeDasharray="4 4" stroke={GRID_STROKE} />
            <XAxis dataKey="label" tick={AXIS_TICK} tickLine={false} axisLine={false} />
            <YAxis
              tick={AXIS_TICK}
              tickLine={false}
              axisLine={false}
              allowDecimals={false}
              width={40}
              tickFormatter={(v: number) => formatCompactNumber(v)}
            />
            <Tooltip content={<MultiTooltip />} cursor={{ stroke: GRID_STROKE }} />
            {series.map((s, i) => (
              <Line
                key={s.key}
                type="monotone"
                dataKey={s.key}
                name={s.label}
                stroke={s.color ?? CHART_PALETTE[i % CHART_PALETTE.length]}
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export type { DashboardMultiSeriesChartProps };
