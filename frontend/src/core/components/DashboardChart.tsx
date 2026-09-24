/**
 * DashboardChart Component
 *
 * Presentational, responsive chart for dashboard "series" widgets. Renders
 * bar / line / area / pie / funnel visualizations with themed axes, gradient
 * fills, direct value labels, a styled tooltip (with share-of-total), smooth
 * entrance animations and (for categorical charts) a legend. No data fetching
 * or business logic.
 */

import { useId, useMemo } from 'react';
import { BarChart3 } from 'lucide-react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Funnel,
  FunnelChart,
  Label,
  LabelList,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { DashboardViz } from '../types';
import { formatCompactNumber } from '../utils';

export const CHART_PALETTE = [
  'var(--color-chart-1)',
  'var(--color-chart-2)',
  'var(--color-chart-3)',
  'var(--color-chart-4)',
  'var(--color-chart-5)',
  'var(--color-chart-6)',
  'var(--color-chart-7)',
  'var(--color-chart-8)',
];

interface SeriesPoint {
  label: string;
  value: number;
  color?: string;
}

interface DashboardChartProps {
  viz: DashboardViz;
  series: SeriesPoint[];
  /** Optional axis titles for cartesian charts (bar/line/area). */
  xLabel?: string;
  yLabel?: string;
}

const AXIS_TICK = { fontSize: 11, fill: 'var(--color-muted-foreground, #6b7280)' };
const AXIS_LABEL_FILL = 'var(--color-muted-foreground, #6b7280)';
const GRID_STROKE = 'var(--color-border, #e5e7eb)';
// Soft, lighter blue used for the line viz to match the gentle area-filled look.
const LINE_STROKE = '#60A5FA';
const ANIM_MS = 600;

const formatAxisTick = (value: number) => formatCompactNumber(value);

// Recharts LabelList formatter passes a RenderableText (string | number |
// undefined); coerce to a number for compact display.
const formatLabelValue = (value: unknown): string => {
  const n = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(n) ? formatCompactNumber(n) : '';
};

interface ChartTooltipProps {
  active?: boolean;
  label?: string | number;
  payload?: { name?: string; value?: number | string; payload?: SeriesPoint & { fill?: string } }[];
  total?: number;
}

function ChartTooltip({ active, payload, label, total }: ChartTooltipProps) {
  if (!active || !payload?.length) return null;
  const point = payload[0];
  const name = label ?? point.name ?? point.payload?.label;
  const numeric = typeof point.value === 'number' ? point.value : Number(point.value);
  const hasShare = total != null && total > 0 && Number.isFinite(numeric);
  const swatch = point.payload?.fill;
  return (
    <div className="rounded-lg border border-border bg-background px-3 py-2 text-xs shadow-md">
      <div className="flex items-center gap-1.5 font-medium text-foreground">
        {swatch && (
          <span
            className="inline-block h-2 w-2 shrink-0 rounded-full"
            style={{ backgroundColor: swatch }}
          />
        )}
        {name}
      </div>
      <div className="mt-0.5 font-mono tabular-nums text-foreground">
        {Number.isFinite(numeric) ? numeric.toLocaleString() : String(point.value)}
        {hasShare && (
          <span className="ml-1.5 font-sans text-muted-foreground">
            ({((numeric / total) * 100).toFixed(1)}%)
          </span>
        )}
      </div>
    </div>
  );
}

function ChartEmpty() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 text-muted-foreground">
      <BarChart3 className="h-8 w-8 opacity-40" strokeWidth={1.5} />
      <span className="text-sm">No data yet</span>
    </div>
  );
}

export default function DashboardChart({ viz, series, xLabel, yLabel }: DashboardChartProps) {
  // Stable, unique gradient ids so multiple charts on one page don't collide.
  const gradientId = useId();
  const areaFill = `area-${gradientId}`;
  const barFill = `bar-${gradientId}`;
  const lineFill = `line-${gradientId}`;

  const colored = useMemo(
    () =>
      series.map((point, i) => ({
        ...point,
        fill: point.color ?? CHART_PALETTE[i % CHART_PALETTE.length],
      })),
    [series],
  );

  const total = useMemo(() => series.reduce((sum, point) => sum + point.value, 0), [series]);

  const funnelConversion = useMemo(
    () =>
      colored.map((point, i) => {
        if (i === 0) return '100%';
        const prev = colored[i - 1].value;
        if (!prev) return '—';
        return `${((point.value / prev) * 100).toFixed(0)}%`;
      }),
    [colored],
  );

  // Recharts axis-title props for cartesian charts; only built when a title is set.
  const xAxisTitle = xLabel
    ? {
        value: xLabel,
        position: 'insideBottom' as const,
        offset: -2,
        style: { fontSize: 11, fill: AXIS_LABEL_FILL, textAnchor: 'middle' as const },
      }
    : undefined;
  const yAxisTitle = yLabel
    ? {
        value: yLabel,
        angle: -90,
        position: 'insideLeft' as const,
        style: { fontSize: 11, fill: AXIS_LABEL_FILL, textAnchor: 'middle' as const },
      }
    : undefined;
  // Extra room so the titles aren't clipped.
  const cartesianMargin = {
    top: 16,
    right: 12,
    bottom: xLabel ? 22 : 0,
    left: yLabel ? 8 : -8,
  };

  if (series.length === 0) {
    return <ChartEmpty />;
  }

  if (viz === 'pie') {
    return (
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={colored}
            dataKey="value"
            nameKey="label"
            innerRadius="48%"
            outerRadius="80%"
            paddingAngle={2}
            cornerRadius={4}
            stroke="var(--color-background, #fff)"
            strokeWidth={2}
            animationDuration={ANIM_MS}
          >
            {colored.map((point) => (
              <Cell key={point.label} fill={point.fill} />
            ))}
            <Label
              position="center"
              content={({ viewBox }) => {
                if (!viewBox || !('cx' in viewBox)) return null;
                const { cx, cy } = viewBox as { cx: number; cy: number };
                return (
                  <g>
                    <text
                      x={cx}
                      y={cy - 4}
                      textAnchor="middle"
                      className="fill-foreground"
                      style={{ fontSize: 20, fontWeight: 600 }}
                    >
                      {formatCompactNumber(total)}
                    </text>
                    <text
                      x={cx}
                      y={cy + 14}
                      textAnchor="middle"
                      className="fill-muted-foreground"
                      style={{ fontSize: 11 }}
                    >
                      Total
                    </text>
                  </g>
                );
              }}
            />
          </Pie>
          <Tooltip content={<ChartTooltip total={total} />} />
          <Legend
            verticalAlign="bottom"
            height={24}
            iconType="circle"
            wrapperStyle={{ fontSize: 11 }}
          />
        </PieChart>
      </ResponsiveContainer>
    );
  }

  if (viz === 'funnel') {
    return (
      <ResponsiveContainer width="100%" height="100%">
        <FunnelChart>
          <Tooltip content={<ChartTooltip total={total} />} />
          <Funnel dataKey="value" data={colored} isAnimationActive animationDuration={ANIM_MS}>
            <LabelList
              position="right"
              dataKey="label"
              className="fill-foreground text-xs"
              stroke="none"
            />
            <LabelList
              position="inside"
              dataKey="value"
              className="fill-white text-xs font-semibold"
              stroke="none"
              formatter={formatLabelValue}
            />
            <LabelList
              position="left"
              dataKey="label"
              stroke="none"
              content={({ index, x, y, height }) => {
                if (typeof index !== 'number' || index === 0) return null;
                const top = typeof y === 'number' ? y : 0;
                const h = typeof height === 'number' ? height : 0;
                const left = typeof x === 'number' ? x : 0;
                return (
                  <text
                    x={left - 8}
                    y={top + h / 2}
                    textAnchor="end"
                    dominantBaseline="middle"
                    className="fill-muted-foreground text-[10px] font-medium"
                  >
                    {funnelConversion[index]}
                  </text>
                );
              }}
            />
            {colored.map((point) => (
              <Cell key={point.label} fill={point.fill} />
            ))}
          </Funnel>
        </FunnelChart>
      </ResponsiveContainer>
    );
  }

  if (viz === 'line') {
    return (
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={series} margin={cartesianMargin}>
          <defs>
            <linearGradient id={lineFill} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={LINE_STROKE} stopOpacity={0.18} />
              <stop offset="100%" stopColor={LINE_STROKE} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} strokeDasharray="4 4" stroke={GRID_STROKE} />
          <XAxis dataKey="label" tick={AXIS_TICK} tickLine={false} axisLine={false} label={xAxisTitle} />
          <YAxis
            tick={AXIS_TICK}
            tickLine={false}
            axisLine={false}
            allowDecimals={false}
            width={40}
            tickFormatter={formatAxisTick}
            label={yAxisTitle}
          />
          <Tooltip content={<ChartTooltip />} cursor={{ stroke: GRID_STROKE }} />
          <Area
            type="natural"
            dataKey="value"
            stroke={LINE_STROKE}
            strokeWidth={2.5}
            fill={`url(#${lineFill})`}
            dot={false}
            activeDot={{ r: 5, fill: LINE_STROKE, strokeWidth: 0 }}
            animationDuration={ANIM_MS}
          />
        </AreaChart>
      </ResponsiveContainer>
    );
  }

  if (viz === 'area') {
    return (
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={series} margin={cartesianMargin}>
          <defs>
            <linearGradient id={areaFill} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={CHART_PALETTE[0]} stopOpacity={0.3} />
              <stop offset="95%" stopColor={CHART_PALETTE[0]} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} strokeDasharray="3 3" stroke={GRID_STROKE} />
          <XAxis dataKey="label" tick={AXIS_TICK} tickLine={false} axisLine={false} label={xAxisTitle} />
          <YAxis
            tick={AXIS_TICK}
            tickLine={false}
            axisLine={false}
            allowDecimals={false}
            width={40}
            tickFormatter={formatAxisTick}
            label={yAxisTitle}
          />
          <Tooltip content={<ChartTooltip />} cursor={{ stroke: GRID_STROKE }} />
          <Area
            type="monotone"
            dataKey="value"
            stroke={CHART_PALETTE[0]}
            strokeWidth={2.5}
            fill={`url(#${areaFill})`}
            dot={{ r: 3, fill: CHART_PALETTE[0], strokeWidth: 0 }}
            activeDot={{ r: 5 }}
            animationDuration={ANIM_MS}
          />
        </AreaChart>
      </ResponsiveContainer>
    );
  }

  if (viz === 'barh') {
    return (
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={colored} layout="vertical" margin={cartesianMargin}>
          <CartesianGrid horizontal={false} strokeDasharray="3 3" stroke={GRID_STROKE} />
          <XAxis
            type="number"
            tick={AXIS_TICK}
            tickLine={false}
            axisLine={false}
            allowDecimals={false}
            tickFormatter={formatAxisTick}
          />
          <YAxis
            type="category"
            dataKey="label"
            tick={AXIS_TICK}
            tickLine={false}
            axisLine={false}
            width={Math.min(180, 8 * Math.max(...colored.map((p) => p.label.length), 4))}
          />
          <Tooltip
            content={<ChartTooltip total={total} />}
            cursor={{ fill: 'var(--color-muted, #f3f4f6)', opacity: 0.4 }}
          />
          <Bar dataKey="value" radius={[0, 4, 4, 0]} maxBarSize={28} animationDuration={ANIM_MS}>
            {colored.map((point) => (
              <Cell key={point.label} fill={point.fill} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    );
  }

  // Show direct value labels only when the series is small enough not to crowd.
  const showBarLabels = colored.length <= 8;

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={colored} margin={cartesianMargin}>
        <defs>
          <linearGradient id={barFill} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={CHART_PALETTE[0]} stopOpacity={1} />
            <stop offset="100%" stopColor={CHART_PALETTE[0]} stopOpacity={0.65} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} strokeDasharray="3 3" stroke={GRID_STROKE} />
        <XAxis dataKey="label" tick={AXIS_TICK} tickLine={false} axisLine={false} label={xAxisTitle} />
        <YAxis
          tick={AXIS_TICK}
          tickLine={false}
          axisLine={false}
          allowDecimals={false}
          width={40}
          tickFormatter={formatAxisTick}
          label={yAxisTitle}
        />
        <Tooltip
          content={<ChartTooltip total={total} />}
          cursor={{ fill: 'var(--color-muted, #f3f4f6)', opacity: 0.4 }}
        />
        <Bar dataKey="value" radius={[4, 4, 0, 0]} maxBarSize={48} animationDuration={ANIM_MS}>
          {colored.map((point) => (
            <Cell key={point.label} fill={point.fill} />
          ))}
          {showBarLabels && (
            <LabelList
              dataKey="value"
              position="top"
              className="fill-muted-foreground text-[10px] font-medium"
              formatter={formatLabelValue}
            />
          )}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export type { DashboardChartProps };
