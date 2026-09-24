import type { ReactNode } from 'react';
import type { Layout } from 'react-grid-layout';

export type DashboardWidgetType = 'kpi' | 'bar' | 'line' | 'area' | 'pie' | 'table';
export type DashboardDatasetId = string;
export type DashboardMetricAggregation = 'sum' | 'avg' | 'min' | 'max' | 'count';
export type DashboardPalette = 'ocean' | 'sunset' | 'forest' | 'mono';
export type DashboardFilterOperator = 'eq' | 'neq' | 'contains' | 'gt' | 'gte' | 'lt' | 'lte' | 'in';

export type DashboardPrimitive = string | number | boolean | null;

export interface DashboardLayoutItem {
  i: string;
  x: number;
  y: number;
  w: number;
  h: number;
  minW?: number;
  minH?: number;
}

export interface DashboardWidgetConfig {
  metricKey?: string;
  format?: 'compact' | 'number' | 'percent' | 'days';
  xKey?: string;
  yKey?: string;
  columns?: string[];
  palette?: DashboardPalette;
  showLegend?: boolean;
  showGrid?: boolean;
  maxItems?: number;
  rowLimit?: number;
}

export interface DashboardWidget {
  id: string;
  title: string;
  type: DashboardWidgetType;
  datasetId: DashboardDatasetId;
  config: DashboardWidgetConfig;
}

export interface DashboardMetricDefinition {
  id: string;
  name: string;
  label: string;
  datasetId: DashboardDatasetId;
  aggregation: DashboardMetricAggregation;
  column?: string;
  format?: 'compact' | 'number' | 'percent' | 'days';
  color?: string;
}

export interface DashboardQuerySelectDefinition {
  field: string;
  alias?: string;
}

export interface DashboardQueryJoinDefinition {
  alias: string;
}

export interface DashboardQueryFilterDefinition {
  field: string;
  op: DashboardFilterOperator;
  value: DashboardPrimitive | DashboardPrimitive[];
}

export interface DashboardQueryAggregationDefinition {
  field: string;
  op: DashboardMetricAggregation;
  alias: string;
}

export interface DashboardQuerySortDefinition {
  field: string;
  direction: 'asc' | 'desc';
}

export interface DashboardQueryDefinition {
  id: string;
  name: string;
  source: string;
  select: DashboardQuerySelectDefinition[];
  joins: DashboardQueryJoinDefinition[];
  filters: DashboardQueryFilterDefinition[];
  group_by: string[];
  aggregations: DashboardQueryAggregationDefinition[];
  sort: DashboardQuerySortDefinition[];
  limit: number;
}

export interface DashboardDocument {
  version: number;
  layout: DashboardLayoutItem[];
  widgets: DashboardWidget[];
  metrics?: DashboardMetricDefinition[];
  queries?: DashboardQueryDefinition[];
  sampleData?: Record<DashboardDatasetId, {
    name?: string;
    rows: Array<Record<string, DashboardPrimitive>>;
  }>;
}

export interface NormalizedDatasetColumn {
  key: string;
  label: string;
  type: 'string' | 'number' | 'boolean';
}

export interface NormalizedDataset {
  id: DashboardDatasetId;
  name: string;
  description?: string;
  columns: NormalizedDatasetColumn[];
  rows: Array<Record<string, DashboardPrimitive>>;
  suggestedVisuals: DashboardWidgetType[];
}

export interface DashboardDefinitionRecord {
  id: string;
  key: string;
  display_name: string;
  description?: string | null;
  config: DashboardDocument;
  is_default: boolean;
  created_at: string;
  updated_at?: string | null;
}

// Editor / form state types used by DashboardPage

export type EditorMode = 'add' | 'edit' | 'metrics' | 'queries';

export interface EditorState {
  open: boolean;
  mode: EditorMode;
  widgetId: string | null;
  metricId: string | null;
}

export interface WidgetFormState {
  title: string;
  type: DashboardWidget['type'];
  datasetId: DashboardDatasetId;
  metricKey: string;
  format: 'compact' | 'number' | 'percent' | 'days';
  xKey: string;
  yKey: string;
  columns: string;
  palette: DashboardPalette;
  showLegend: boolean;
  showGrid: boolean;
  maxItems: string;
  rowLimit: string;
}

export interface MetricFormState {
  id: string;
  name: string;
  label: string;
  datasetId: DashboardDatasetId;
  aggregation: DashboardMetricAggregation;
  column: string;
  format: 'compact' | 'number' | 'percent' | 'days';
  color: string;
}

export interface QueryFormState {
  id: string;
  name: string;
  source: string;
  limit: string;
  selectedFields: string[];
  selectedJoins: string[];
  groupBy: string[];
  filterField: string;
  filterOp: DashboardFilterOperator;
  filterValue: string;
  filters: Array<{ field: string; op: DashboardFilterOperator; value: string }>;
  aggregationField: string;
  aggregationOp: DashboardMetricAggregation;
  aggregationAlias: string;
  aggregations: Array<{ field: string; op: DashboardMetricAggregation; alias: string }>;
}

export interface DashboardCanvasProps {
  widgets: DashboardWidget[];
  datasets: Record<DashboardDatasetId, NormalizedDataset>;
  responsiveLayouts: Partial<Record<string, Layout>>;
  gridWidth: number;
  onLayoutChange: (layout: Layout) => void;
  onEditWidget: (widget: DashboardWidget) => void;
  onRemoveWidget: (widgetId: string) => void;
}

export interface DashboardCanvasBoundaryState {
  hasError: boolean;
}

export interface DashboardCanvasBoundaryProps extends DashboardCanvasProps {
  fallback: (props: DashboardCanvasProps) => ReactNode;
  children: ReactNode;
}

export interface DashboardWidgetCardProps {
  widget: DashboardWidget;
  dataset?: NormalizedDataset;
  onEditWidget: (widget: DashboardWidget) => void;
  onRemoveWidget: (widgetId: string) => void;
}
