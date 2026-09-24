import type {
  DashboardMetricRead,
  DashboardViz,
  DashboardWidgetDef,
  DashboardWidgetType,
} from '../../../core/types';
import { type BuilderState, EMPTY_BUILDER, SERIES_VIZ } from './constants';

export function widgetTypeForOutput(output: DashboardMetricRead['output']): DashboardWidgetType {
  if (output === 'scalar') return 'stat';
  if (output === 'rows') return 'table';
  if (output === 'gauge') return 'gauge';
  return 'chart';
}

export function defaultLayoutForType(type: DashboardWidgetType) {
  switch (type) {
    // Widths are in 60-col units. Stat defaults to 10 (6 per row); resize to 12
    // for a clean 5-across. Others mirror the old 12-col ratios (×5).
    case 'stat':
      return { w: 10, h: 2 };
    case 'gauge':
      return { w: 15, h: 3 };
    case 'button':
      return { w: 15, h: 3 };
    case 'content':
      return { w: 30, h: 3 };
    default:
      return { w: 30, h: 5 };
  }
}

export function vizForOutput(metric: DashboardMetricRead): DashboardViz {
  if (metric.output === 'scalar') return 'number';
  if (metric.output === 'rows') return 'table';
  if (metric.output === 'gauge') return 'gauge';
  if (metric.output === 'multiseries') return 'line';
  return (metric.default_visuals[0] as DashboardViz) ?? 'bar';
}

export function vizOptionsFor(): { value: DashboardViz; label: string }[] {
  return SERIES_VIZ;
}

export function builderFromWidget(widget: DashboardWidgetDef): BuilderState {
  const kind = widget.type as BuilderState['kind'];
  if (kind === 'button') {
    return {
      ...EMPTY_BUILDER,
      kind,
      title: widget.title,
      description: widget.description ?? '',
      href: widget.href ?? '',
      icon: widget.icon ?? '',
    };
  }
  if (kind === 'content') {
    return {
      ...EMPTY_BUILDER,
      kind,
      title: widget.title,
      elements: widget.elements ?? [],
      verticalAlign: widget.verticalAlign ?? 'top',
    };
  }
  if (kind === 'embedded') {
    return {
      ...EMPTY_BUILDER,
      kind,
      title: widget.title,
      componentKey: widget.componentKey ?? '',
      componentConfig: widget.componentConfig ?? {},
    };
  }
  if (widget.type === 'query' || widget.query) {
    return {
      ...EMPTY_BUILDER,
      kind: 'query',
      title: widget.title,
      viz: widget.viz ?? 'bar',
      query: widget.query ?? null,
    };
  }
  const rawFilters = widget.filters ?? {};
  const fields = Array.isArray(rawFilters.fields) ? (rawFilters.fields as string[]) : [];
  const states = Array.isArray(rawFilters.states) ? (rawFilters.states as string[]) : [];
  const metadataTypes = Array.isArray(rawFilters.metadata_type)
    ? (rawFilters.metadata_type as string[])
    : [];
  const filters: Record<string, string> = {};
  for (const [key, value] of Object.entries(rawFilters)) {
    if (key === 'fields' || key === 'states' || key === 'metadata_type' || value == null) continue;
    filters[key] = String(value);
  }
  return {
    ...EMPTY_BUILDER,
    kind,
    title: widget.title,
    description: widget.description ?? '',
    href: widget.href ?? '',
    metric: widget.metric ?? '',
    viz: widget.viz ?? 'bar',
    filters,
    fields,
    states,
    metadataTypes,
    icon: widget.icon ?? '',
    xAxisLabel: widget.xAxisLabel ?? '',
    yAxisLabel: widget.yAxisLabel ?? '',
    subtitle: widget.subtitle ?? '',
  };
}
