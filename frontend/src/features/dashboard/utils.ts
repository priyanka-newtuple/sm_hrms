import type { LayoutItem } from 'react-grid-layout';

import type {
  DashboardDatasetId,
  DashboardLayoutItem,
  DashboardMetricDefinition,
  DashboardQueryDefinition,
  DashboardWidget,
  EditorState,
  MetricFormState,
  NormalizedDataset,
  QueryFormState,
  WidgetFormState,
} from './types';

export const DEFAULT_EDITOR_STATE: EditorState = {
  open: false,
  mode: 'add',
  widgetId: null,
  metricId: null,
};

export const BREAKPOINTS = { lg: 1200, md: 996, sm: 768, xs: 480, xxs: 0 } as const;
export const RESPONSIVE_COLS = { lg: 12, md: 10, sm: 6, xs: 4, xxs: 2 } as const;

export function fromLayout(items: LayoutItem[]): DashboardLayoutItem[] {
  return items.map((item) => ({
    i: item.i,
    x: item.x,
    y: item.y,
    w: item.w,
    h: item.h,
    minW: item.minW,
    minH: item.minH,
  }));
}

export function getDefaultLayout(widgetId: string, type: DashboardWidget['type']): DashboardLayoutItem {
  const isKpi = type === 'kpi';
  return {
    i: widgetId,
    x: 0,
    y: Number.MAX_SAFE_INTEGER,
    w: isKpi ? 3 : 6,
    h: isKpi ? 2 : 5,
    minW: isKpi ? 2 : 4,
    minH: isKpi ? 2 : 4,
  };
}

function sortLayoutItems(items: DashboardLayoutItem[]): DashboardLayoutItem[] {
  return [...items].sort((a, b) => (a.y - b.y) || (a.x - b.x));
}

function makeResponsiveLayout(items: DashboardLayoutItem[], columns: number): LayoutItem[] {
  const ordered = sortLayoutItems(items);
  let cursorX = 0;
  let cursorY = 0;
  let rowHeight = 0;

  return ordered.map((item) => {
    const width = columns >= 10
      ? Math.min(item.w, columns)
      : columns >= 6
        ? Math.min(Math.max(item.w >= 6 ? columns : Math.ceil(columns / 2), 2), columns)
        : columns;

    if (cursorX + width > columns) {
      cursorX = 0;
      cursorY += rowHeight;
      rowHeight = 0;
    }

    const nextItem: LayoutItem = {
      ...item,
      x: cursorX,
      y: cursorY,
      w: width,
      h: item.h,
      minW: Math.min(item.minW ?? 1, width),
    };

    cursorX += width;
    rowHeight = Math.max(rowHeight, item.h);
    return nextItem;
  });
}

export function buildResponsiveLayouts(items: DashboardLayoutItem[]) {
  return {
    lg: makeResponsiveLayout(items, RESPONSIVE_COLS.lg),
    md: makeResponsiveLayout(items, RESPONSIVE_COLS.md),
    sm: makeResponsiveLayout(items, RESPONSIVE_COLS.sm),
    xs: makeResponsiveLayout(items, RESPONSIVE_COLS.xs),
    xxs: makeResponsiveLayout(items, RESPONSIVE_COLS.xxs),
  };
}

export function toFormState(widget?: DashboardWidget): WidgetFormState {
  return {
    title: widget?.title ?? '',
    type: widget?.type ?? 'table',
    datasetId: widget?.datasetId ?? 'pipeline',
    metricKey: widget?.config.metricKey ?? '',
    format: widget?.config.format ?? 'number',
    xKey: widget?.config.xKey ?? '',
    yKey: widget?.config.yKey ?? '',
    columns: widget?.config.columns?.join(', ') ?? '',
    palette: widget?.config.palette ?? 'ocean',
    showLegend: widget?.config.showLegend ?? true,
    showGrid: widget?.config.showGrid ?? true,
    maxItems: String(widget?.config.maxItems ?? 12),
    rowLimit: String(widget?.config.rowLimit ?? 20),
  };
}

export function toMetricFormState(metric?: DashboardMetricDefinition): MetricFormState {
  return {
    id: metric?.id ?? '',
    name: metric?.name ?? '',
    label: metric?.label ?? '',
    datasetId: metric?.datasetId ?? 'pipeline',
    aggregation: metric?.aggregation ?? 'count',
    column: metric?.column ?? '',
    format: metric?.format ?? 'number',
    color: metric?.color ?? '#0F4C81',
  };
}

export function toQueryFormState(query?: DashboardQueryDefinition): QueryFormState {
  return {
    id: query?.id ?? '',
    name: query?.name ?? '',
    source: query?.source ?? 'application_pipeline',
    limit: String(query?.limit ?? 100),
    selectedFields: query?.select.map((item) => item.field) ?? [],
    selectedJoins: query?.joins.map((item) => item.alias) ?? [],
    groupBy: query?.group_by ?? [],
    filterField: '',
    filterOp: 'eq',
    filterValue: '',
    filters: (query?.filters ?? []).map((item) => ({ field: item.field, op: item.op, value: String(item.value ?? '') })),
    aggregationField: '*',
    aggregationOp: 'count',
    aggregationAlias: '',
    aggregations: query?.aggregations.map((item) => ({ field: item.field, op: item.op, alias: item.alias })) ?? [],
  };
}

export function widgetTypeDescription(type: DashboardWidget['type']): string {
  if (type === 'kpi') return 'Single metric card for one numeric field or reusable metric.';
  if (type === 'table') return 'Tabular view where you choose exactly which columns to show.';
  if (type === 'pie') return 'Part-to-whole comparison. Best for grouped category counts or risk split.';
  if (type === 'line') return 'Trend chart for ordered categories or time-like sequences.';
  if (type === 'area') return 'Trend chart with filled area to emphasize volume over a sequence.';
  return 'Category comparison chart using one label column and one numeric value column.';
}

export function createMetricId(): string {
  return `metric-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function createQueryId(): string {
  return `query-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function getDatasetNumericColumns(dataset?: NormalizedDataset) {
  return (dataset?.columns ?? [])
    .filter((column) => column.type === 'number')
    .map((column) => ({ value: column.key, label: column.label }));
}

export function getDatasetOptions(datasets: Record<DashboardDatasetId, NormalizedDataset>) {
  return Object.values(datasets)
    .sort((a, b) => a.name.localeCompare(b.name))
    .map((dataset) => ({ value: dataset.id, label: dataset.name }));
}

export function getWidgetGridClass(type: DashboardWidget['type']): string {
  return type === 'kpi' ? 'xl:col-span-3' : 'xl:col-span-6';
}

export function isSeriesWidgetType(type: DashboardWidget['type']): boolean {
  return type === 'bar' || type === 'pie' || type === 'line' || type === 'area';
}
