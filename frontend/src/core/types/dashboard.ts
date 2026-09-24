export interface DashboardDefinitionRead {
  id: string;
  key: string;
  display_name: string;
  description?: string | null;
  config: Record<string, unknown>;
  is_default: boolean;
  created_at: string;
  updated_at?: string | null;
}

export interface DashboardDefinitionUpdate {
  display_name?: string;
  description?: string | null;
  config: Record<string, unknown>;
}

export type DashboardWidgetType =
  | 'stat'
  | 'chart'
  | 'table'
  | 'button'
  | 'gauge'
  | 'query'
  | 'activity'
  | 'embedded'
  | 'content';

export interface DashboardContentElement {
  id: string;
  kind: 'header' | 'text' | 'button';
  text: string;
  /** Button elements only: navigation target. */
  href?: string;
  /** Horizontal alignment within the widget. Absent = 'left'. */
  align?: 'left' | 'center' | 'right';
}
export type DashboardViz =
  | 'number'
  | 'bar'
  | 'barh'
  | 'line'
  | 'area'
  | 'pie'
  | 'funnel'
  | 'table'
  | 'gauge';

export interface DashboardWidgetLayout {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface DashboardWidgetDef {
  id: string;
  type: DashboardWidgetType;
  title: string;
  metric?: string;
  filters?: Record<string, unknown>;
  viz?: DashboardViz;
  layout: DashboardWidgetLayout;
  /** Button widgets: navigation target. Other widgets: makes the header title a link. */
  href?: string;
  /** Button widgets: supporting text above the button. Other widgets: subtext under the header title. */
  description?: string;
  /** For button widgets: optional Lucide icon name shown beside the label. */
  icon?: string;
  /** Content-block widgets: ordered header/text/button elements stacked in the block. */
  elements?: DashboardContentElement[];
  /** Content-block widgets: vertical position of the stacked elements within the grid cell. Absent = 'top'. */
  verticalAlign?: 'top' | 'middle' | 'bottom';
  /** For cartesian charts (bar/line/area): optional axis titles. */
  xAxisLabel?: string;
  yAxisLabel?: string;
  /** For stat widgets: optional supporting line under the value. `{value}` is substituted. */
  subtitle?: string;
  /** Query-backed widget: an inline query definition (alternative to `metric`). */
  query?: DashboardQueryDefinitionRequest;
  /** Embedded widgets: key into the curated frontend registry (e.g. "workflows.list"). */
  componentKey?: string;
  /** Embedded widgets: per-widget config passed to the registered component. */
  componentConfig?: Record<string, unknown>;
}

export interface DashboardConfig {
  version?: number;
  /** Grid column count the widget layouts are expressed in. Absent = legacy 12-col. */
  cols?: number;
  widgets: DashboardWidgetDef[];
}

export type DashboardFilterSource =
  | 'workflows'
  | 'entity_types'
  | 'states'
  | 'event_types'
  | 'entity_fields';

export interface DashboardMetricParamRead {
  key: string;
  label: string;
  type: 'string' | 'number' | 'date';
  source?: DashboardFilterSource | null;
}

export interface DashboardMetricFieldRead {
  key: string;
  label: string;
}

export interface DashboardMetricRead {
  key: string;
  label: string;
  description: string;
  output: 'series' | 'scalar' | 'rows' | 'gauge' | 'multiseries';
  default_visuals: string[];
  params: DashboardMetricParamRead[];
  fields: DashboardMetricFieldRead[];
}

export interface DashboardMetricsResponse {
  metrics: DashboardMetricRead[];
  fields_scoped: boolean;
}

export interface DashboardDataItem {
  widget_id: string;
  metric?: string;
  query?: DashboardQueryDefinitionRequest;
  filters?: Record<string, unknown>;
}

export interface DashboardDataRequest {
  items: DashboardDataItem[];
  anchor_entity_id?: string | null;
}

export interface DashboardSeriesPoint {
  label: string;
  value: number;
  color?: string;
}

export interface DashboardTableColumn {
  key: string;
  label: string;
}

export interface DashboardMultiSeriesDef {
  key: string;
  label: string;
  color?: string;
}

export type DashboardWidgetData =
  | { kind: 'series'; series: DashboardSeriesPoint[] }
  | {
      kind: 'scalar';
      value: number;
      prevValue?: number;
    }
  | {
      kind: 'rows';
      columns: DashboardTableColumn[];
      rows: Record<string, unknown>[];
    }
  | { kind: 'gauge'; value: number; max: number; label?: string }
  | {
      kind: 'multiseries';
      points: Array<{ label: string } & Record<string, number>>;
      series: DashboardMultiSeriesDef[];
    }
  | { kind: 'error'; error: string };

export interface DashboardDataResponse {
  results: Record<string, DashboardWidgetData>;
}

export interface DashboardFilterOption {
  value: string;
  label: string;
}

export interface DashboardFilterOptionsResponse {
  workflows: DashboardFilterOption[];
  entity_types: DashboardFilterOption[];
  states: DashboardFilterOption[];
  event_types: DashboardFilterOption[];
  entity_fields: DashboardFilterOption[];
}

export interface DashboardQueryFieldRead {
  key: string;
  label: string;
  type: 'string' | 'number' | 'boolean' | 'date';
  groupable: boolean;
  filterable: boolean;
  aggregatable: boolean;
}

export interface DashboardQueryJoinRead {
  alias: string;
  label: string;
  description?: string | null;
  fields: DashboardQueryFieldRead[];
}

export interface DashboardQuerySourceRead {
  id: string;
  label: string;
  description?: string | null;
  fields: DashboardQueryFieldRead[];
  joins: DashboardQueryJoinRead[];
}

export interface DashboardQuerySourcesResponse {
  sources: DashboardQuerySourceRead[];
}

export interface DashboardQuerySelectRequest {
  field: string;
  alias?: string;
}

export interface DashboardQueryJoinRequest {
  alias: string;
}

export interface DashboardQueryFilterRequest {
  field: string;
  op: 'eq' | 'neq' | 'contains' | 'gt' | 'gte' | 'lt' | 'lte' | 'in';
  value: unknown;
}

export interface DashboardQueryAggregationRequest {
  field: string;
  op: 'count' | 'sum' | 'avg' | 'min' | 'max';
  alias: string;
}

export interface DashboardQuerySortRequest {
  field: string;
  direction: 'asc' | 'desc';
}

export interface DashboardQueryDefinitionRequest {
  id?: string;
  name?: string;
  source: string;
  select: DashboardQuerySelectRequest[];
  joins: DashboardQueryJoinRequest[];
  filters: DashboardQueryFilterRequest[];
  group_by: string[];
  aggregations: DashboardQueryAggregationRequest[];
  sort: DashboardQuerySortRequest[];
  limit: number;
}

export interface DashboardQueryPreviewResponse {
  source: string;
  columns: DashboardQueryFieldRead[];
  rows: Array<Record<string, unknown>>;
  row_count: number;
  suggested_visuals: Array<'kpi' | 'bar' | 'line' | 'area' | 'pie' | 'table'>;
}
