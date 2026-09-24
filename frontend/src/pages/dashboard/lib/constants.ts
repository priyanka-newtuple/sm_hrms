import { AppWindow, BarChart3, Gauge, Hash, History, Layers, MousePointerClick, Rows3, Table, type LucideIcon } from 'lucide-react';
import type {
  DashboardContentElement,
  DashboardFilterOptionsResponse,
  DashboardMetricRead,
  DashboardQueryDefinitionRequest,
  DashboardViz,
  DashboardWidgetDef,
} from '../../../core/types';

export const ROW_HEIGHT = 80;
export const GRID_MARGIN: readonly [number, number] = [10, 10];

// Grid columns. 60 = LCM(5,6,12,...), so 5 (w=12), 6 (w=10), 4, 3, 2 cards all
// fit a row edge-to-edge. Legacy dashboards were stored on a 12-col grid and
// are rescaled ×LEGACY_GRID_SCALE on load (×5 preserves every widget's ratio).
export const GRID_COLS = 60;
export const LEGACY_GRID_SCALE = GRID_COLS / 12;

export const EMPTY_FILTER_OPTIONS: DashboardFilterOptionsResponse = {
  workflows: [],
  entity_types: [],
  states: [],
  event_types: [],
  entity_fields: [],
};

export const SERIES_VIZ: { value: DashboardViz; label: string }[] = [
  { value: 'bar', label: 'Bar' },
  { value: 'line', label: 'Line' },
  { value: 'area', label: 'Area' },
  { value: 'pie', label: 'Pie' },
  { value: 'funnel', label: 'Funnel' },
];

export const NUMBER_PRESETS: Record<string, { value: string; label: string }[]> = {
  days: [
    { value: '7', label: 'Last 7 days' },
    { value: '14', label: 'Last 14 days' },
    { value: '30', label: 'Last 30 days' },
    { value: '90', label: 'Last 90 days' },
  ],
  limit: [
    { value: '10', label: '10 rows' },
    { value: '25', label: '25 rows' },
    { value: '50', label: '50 rows' },
    { value: '100', label: '100 rows' },
  ],
  // Custom timeline bucket for multi-line trend metrics (rendered as a dropdown).
  bucket: [
    { value: 'day', label: 'Daily' },
    { value: 'week', label: 'Weekly' },
    { value: 'month', label: 'Monthly' },
  ],
};

// The only metric shaped for DashboardActivityList (event_type/entity_type/occurred_at
// fields). Other 'rows' metrics (e.g. instances.list) render as a plain table instead.
export const ACTIVITY_METRIC_KEY = 'events.activity';

// Audit metadata_type categories for the Activity list widget's multi-select.
export const METADATA_TYPE_OPTIONS: { key: string; label: string }[] = [
  { key: 'entity', label: 'Entity' },
  { key: 'transition', label: 'Transition' },
  { key: 'auth', label: 'Auth' },
];

export type WidgetKind =
  | 'stat'
  | 'table'
  | 'chart'
  | 'button'
  | 'gauge'
  | 'query'
  | 'activity'
  | 'embedded'
  | 'content';

export const WIDGET_KINDS: {
  value: WidgetKind;
  label: string;
  description: string;
  icon: LucideIcon;
}[] = [
  { value: 'stat', label: 'Stat', description: 'A single number', icon: Hash },
  { value: 'table', label: 'Table', description: 'A list of rows', icon: Table },
  { value: 'activity', label: 'Activity list', description: 'Audit-log timeline', icon: History },
  { value: 'chart', label: 'Chart', description: 'Bar, line, pie…', icon: BarChart3 },
  { value: 'gauge', label: 'Gauge', description: 'A ratio dial', icon: Gauge },
  { value: 'button', label: 'Button card', description: 'A card with a link action', icon: MousePointerClick },
  { value: 'query', label: 'Query', description: 'Group-by any field', icon: Layers },
  { value: 'embedded', label: 'Embedded', description: 'Interactive app view', icon: AppWindow },
  { value: 'content', label: 'Content block', description: 'Stack headers, text and buttons', icon: Rows3 },
];

export const KIND_OUTPUT: Record<
  Exclude<WidgetKind, 'button' | 'query' | 'embedded' | 'content'>,
  DashboardMetricRead['output']
> = {
  stat: 'scalar',
  table: 'rows',
  chart: 'series',
  gauge: 'gauge',
  activity: 'rows',
};

export const CARTESIAN_VIZ: DashboardViz[] = ['bar', 'line', 'area'];

export const CONTENT_ELEMENT_KINDS: { value: DashboardContentElement['kind']; label: string }[] = [
  { value: 'header', label: 'Header' },
  { value: 'text', label: 'Text' },
  { value: 'button', label: 'Button' },
];

export const ALIGN_OPTIONS: { value: NonNullable<DashboardContentElement['align']>; label: string }[] = [
  { value: 'left', label: 'Left' },
  { value: 'center', label: 'Center' },
  { value: 'right', label: 'Right' },
];

export const VERTICAL_ALIGN_OPTIONS: {
  value: NonNullable<DashboardWidgetDef['verticalAlign']>;
  label: string;
}[] = [
  { value: 'top', label: 'Top' },
  { value: 'middle', label: 'Middle' },
  { value: 'bottom', label: 'Bottom' },
];

export interface BuilderState {
  kind: WidgetKind;
  title: string;
  description: string;
  metric: string;
  viz: DashboardViz;
  filters: Record<string, string>;
  fields: string[];
  /** Selected states to plot for multi-line state trends (empty = all). */
  states: string[];
  /** Selected audit metadata categories for the Activity list widget (empty = all). */
  metadataTypes: string[];
  href: string;
  icon: string;
  /** Content-block widgets: ordered header/text/button elements being edited. */
  elements: DashboardContentElement[];
  /** Content-block widgets: vertical position of the stacked elements in the cell. */
  verticalAlign: 'top' | 'middle' | 'bottom';
  xAxisLabel: string;
  yAxisLabel: string;
  subtitle: string;
  query: DashboardQueryDefinitionRequest | null;
  /** Embedded widgets: selected registry key + its config blob. */
  componentKey: string;
  componentConfig: Record<string, unknown>;
}

export const EMPTY_BUILDER: BuilderState = {
  kind: 'stat',
  title: '',
  description: '',
  metric: '',
  viz: 'bar',
  filters: {},
  fields: [],
  states: [],
  metadataTypes: [],
  href: '',
  icon: '',
  elements: [],
  verticalAlign: 'top',
  xAxisLabel: '',
  yAxisLabel: '',
  subtitle: '',
  query: null,
  componentKey: '',
  componentConfig: {},
};
