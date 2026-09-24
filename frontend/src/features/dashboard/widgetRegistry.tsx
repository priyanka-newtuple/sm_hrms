import type { ReactNode } from 'react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { EmptyState } from '../../core/components';
import type { DashboardPalette, DashboardPrimitive, DashboardWidget, NormalizedDataset } from './types';

interface WidgetRendererProps {
  widget: DashboardWidget;
  dataset?: NormalizedDataset;
}

const PALETTES: Record<DashboardPalette, string[]> = {
  ocean: ['#0F4C81', '#118AB2', '#06D6A0', '#83C5BE', '#3A86FF', '#8ECAE6'],
  sunset: ['#F97316', '#FB7185', '#F59E0B', '#EF4444', '#F43F5E', '#FDBA74'],
  forest: ['#166534', '#22C55E', '#0F766E', '#84CC16', '#4D7C0F', '#2DD4BF'],
  mono: ['#0F172A', '#334155', '#64748B', '#94A3B8', '#CBD5E1', '#E2E8F0'],
};

function getPalette(palette?: DashboardPalette): string[] {
  return PALETTES[palette ?? 'ocean'];
}

function formatValue(value: DashboardPrimitive, format?: string): string {
  if (typeof value !== 'number') return String(value ?? '0');
  if (format === 'compact') {
    return new Intl.NumberFormat('en-IN', { notation: 'compact', maximumFractionDigits: 1 }).format(value);
  }
  if (format === 'percent') {
    return `${Math.round(value * 100)}%`;
  }
  if (format === 'days') {
    return value < 1 ? `${Math.round(value * 24)}h` : `${value.toFixed(1)}d`;
  }
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 }).format(value);
}

function getChartRows(widget: DashboardWidget, dataset?: NormalizedDataset) {
  const maxItems = widget.config.maxItems && widget.config.maxItems > 0 ? widget.config.maxItems : 12;
  return (dataset?.rows ?? []).slice(0, maxItems);
}

function renderGrid(enabled?: boolean) {
  if (!enabled) return null;
  return <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="#E2E8F0" />;
}

function renderLegend(enabled?: boolean) {
  if (!enabled) return null;
  return <Legend wrapperStyle={{ fontSize: '12px' }} />;
}

function KpiWidget({ widget, dataset }: WidgetRendererProps) {
  const row = dataset?.rows[0];
  const value = row?.[widget.config.metricKey ?? ''];
  const palette = getPalette(widget.config.palette);
  return (
    <div
      className="flex h-full min-h-[132px] flex-col justify-between rounded-3xl px-5 py-4 text-white"
      style={{ background: `linear-gradient(135deg, ${palette[0]} 0%, ${palette[1] ?? palette[0]} 100%)` }}
    >
      <div className="text-sm text-white/75">{dataset?.name ?? 'Summary'}</div>
      <div className="pt-4 text-4xl font-semibold tracking-tight sm:text-5xl">{formatValue(value ?? 0, widget.config.format)}</div>
      <div className="pt-2 text-xs uppercase tracking-[0.16em] text-white/70">
        {widget.config.metricKey?.replaceAll('_', ' ') ?? 'metric'}
      </div>
    </div>
  );
}

function BarChartWidget({ widget, dataset }: WidgetRendererProps) {
  const rows = getChartRows(widget, dataset);
  if (!dataset || rows.length === 0) {
    return <EmptyState surface="plain" title="No chart data" description="This dataset is currently empty." />;
  }

  const palette = getPalette(widget.config.palette);
  return (
    <ResponsiveContainer width="100%" height="100%" minHeight={260}>
      <BarChart data={rows}>
        {renderGrid(widget.config.showGrid)}
        <XAxis dataKey={widget.config.xKey} tickLine={false} axisLine={false} fontSize={12} />
        <YAxis tickLine={false} axisLine={false} fontSize={12} allowDecimals={false} />
        <Tooltip />
        {renderLegend(widget.config.showLegend)}
        <Bar dataKey={widget.config.yKey} radius={[10, 10, 0, 0]} name={widget.title}>
          {rows.map((entry, index) => (
            <Cell
              key={String(entry[widget.config.xKey ?? ''] ?? index)}
              fill={String(entry.color ?? palette[index % palette.length])}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function LineChartWidget({ widget, dataset }: WidgetRendererProps) {
  const rows = getChartRows(widget, dataset);
  if (!dataset || rows.length === 0) {
    return <EmptyState surface="plain" title="No chart data" description="This dataset is currently empty." />;
  }

  const palette = getPalette(widget.config.palette);
  return (
    <ResponsiveContainer width="100%" height="100%" minHeight={260}>
      <LineChart data={rows}>
        {renderGrid(widget.config.showGrid)}
        <XAxis dataKey={widget.config.xKey} tickLine={false} axisLine={false} fontSize={12} />
        <YAxis tickLine={false} axisLine={false} fontSize={12} />
        <Tooltip />
        {renderLegend(widget.config.showLegend)}
        <Line
          type="monotone"
          dataKey={widget.config.yKey}
          name={widget.title}
          stroke={palette[0]}
          strokeWidth={3}
          dot={{ r: 4, fill: palette[1] ?? palette[0] }}
          activeDot={{ r: 6 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

function AreaChartWidget({ widget, dataset }: WidgetRendererProps) {
  const rows = getChartRows(widget, dataset);
  if (!dataset || rows.length === 0) {
    return <EmptyState surface="plain" title="No chart data" description="This dataset is currently empty." />;
  }

  const palette = getPalette(widget.config.palette);
  return (
    <ResponsiveContainer width="100%" height="100%" minHeight={260}>
      <AreaChart data={rows}>
        {renderGrid(widget.config.showGrid)}
        <XAxis dataKey={widget.config.xKey} tickLine={false} axisLine={false} fontSize={12} />
        <YAxis tickLine={false} axisLine={false} fontSize={12} />
        <Tooltip />
        {renderLegend(widget.config.showLegend)}
        <Area
          type="monotone"
          dataKey={widget.config.yKey ?? 'value'}
          name={widget.title}
          stroke={palette[0]}
          fill={palette[1] ?? palette[0]}
          fillOpacity={0.3}
          strokeWidth={3}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

function PieChartWidget({ widget, dataset }: WidgetRendererProps) {
  const rows = getChartRows(widget, dataset);
  if (!dataset || rows.length === 0) {
    return <EmptyState surface="plain" title="No chart data" description="This dataset is currently empty." />;
  }

  const palette = getPalette(widget.config.palette);
  return (
    <div className="grid h-full min-h-[260px] grid-cols-1 items-center gap-4 lg:grid-cols-[1fr_180px]">
      <ResponsiveContainer width="100%" height="100%" minHeight={260}>
        <PieChart>
          <Pie
            data={rows}
            dataKey={widget.config.yKey}
            nameKey={widget.config.xKey}
            innerRadius={52}
            outerRadius={88}
            paddingAngle={3}
          >
            {rows.map((entry, index) => (
              <Cell
                key={String(entry[widget.config.xKey ?? ''] ?? index)}
                fill={String(entry.color ?? palette[index % palette.length])}
              />
            ))}
          </Pie>
          <Tooltip />
          {renderLegend(widget.config.showLegend)}
        </PieChart>
      </ResponsiveContainer>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 lg:grid-cols-1">
        {rows.map((entry, index) => (
          <div key={String(entry[widget.config.xKey ?? ''] ?? index)} className="rounded-2xl bg-muted/50 p-3">
            <div className="text-xs uppercase tracking-[0.14em] text-muted-foreground">
              {String(entry[widget.config.xKey ?? ''] ?? 'Series')}
            </div>
            <div className="mt-2 text-2xl font-semibold text-foreground">
              {formatValue(entry[widget.config.yKey ?? ''] ?? 0)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function TableWidget({ widget, dataset }: WidgetRendererProps) {
  if (!dataset || dataset.rows.length === 0) {
    return <EmptyState surface="plain" title="No rows" description="This dataset is currently empty." />;
  }

  const columns = widget.config.columns?.length ? widget.config.columns : dataset.columns.slice(0, 5).map((column) => column.key);
  const rowLimit = widget.config.rowLimit && widget.config.rowLimit > 0 ? widget.config.rowLimit : 20;

  return (
    <div className="h-full min-h-[260px] overflow-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="sticky top-0 bg-card">
          <tr className="border-b border-border">
            {columns.map((column) => (
              <th key={column} className="px-3 py-2 font-medium text-muted-foreground">
                {dataset.columns.find((datasetColumn) => datasetColumn.key === column)?.label ?? column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {dataset.rows.slice(0, rowLimit).map((row, index) => (
            <tr key={index} className="border-b border-border last:border-0">
              {columns.map((column) => (
                <td key={column} className="px-3 py-2 text-foreground">
                  {String(row[column] ?? '—')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const registry: Record<DashboardWidget['type'], (props: WidgetRendererProps) => ReactNode> = {
  kpi: KpiWidget,
  bar: BarChartWidget,
  line: LineChartWidget,
  area: AreaChartWidget,
  pie: PieChartWidget,
  table: TableWidget,
};

export function DashboardWidgetRenderer({ widget, dataset }: WidgetRendererProps) {
  const Component = registry[widget.type];
  if (!Component) {
    return (
      <EmptyState
        surface="plain"
        title="Unsupported widget"
        description={`The saved widget type "${widget.type}" is not available in this dashboard build.`}
      />
    );
  }

  try {
    return <>{Component({ widget, dataset })}</>;
  } catch {
    return (
      <EmptyState
        surface="plain"
        title="Widget failed to render"
        description="This widget configuration is invalid for the current dataset. Edit the widget and update its bindings."
      />
    );
  }
}
