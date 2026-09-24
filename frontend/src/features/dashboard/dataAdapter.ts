import type {
  DashboardQueryPreviewResponse,
  DashboardQuerySourceRead,
} from '../../core/types';
import type {
  DashboardDatasetId,
  DashboardDocument,
  DashboardMetricDefinition,
  DashboardPrimitive,
  DashboardWidget,
  NormalizedDataset,
} from './types';

function inferColumnType(values: DashboardPrimitive[]): 'string' | 'number' | 'boolean' {
  const nonNull = values.filter((value) => value !== null);
  if (nonNull.every((value) => typeof value === 'number')) return 'number';
  if (nonNull.every((value) => typeof value === 'boolean')) return 'boolean';
  return 'string';
}

function titleize(key: string): string {
  return key
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function buildDataset(
  id: DashboardDatasetId,
  name: string,
  rows: Array<Record<string, DashboardPrimitive>>,
  suggestedVisuals: NormalizedDataset['suggestedVisuals'],
  description?: string,
): NormalizedDataset {
  const keys = new Set<string>();
  for (const row of rows) {
    Object.keys(row).forEach((key) => keys.add(key));
  }

  const columns = Array.from(keys).map((key) => ({
    key,
    label: titleize(key),
    type: inferColumnType(rows.map((row) => row[key] ?? null)),
  }));

  return { id, name, description, rows, columns, suggestedVisuals };
}

function average(values: number[]): number {
  if (values.length === 0) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function computeMetricValue(
  rows: Array<Record<string, DashboardPrimitive>>,
  aggregation: DashboardMetricDefinition['aggregation'],
  column?: string,
): number {
  if (aggregation === 'count') {
    return rows.length;
  }

  if (!column) return 0;

  const values = rows
    .map((row) => row[column])
    .filter((value): value is number => typeof value === 'number');

  if (values.length === 0) return 0;
  if (aggregation === 'sum') return Number(values.reduce((sum, value) => sum + value, 0).toFixed(2));
  if (aggregation === 'avg') return Number(average(values).toFixed(2));
  if (aggregation === 'min') return Math.min(...values);
  return Math.max(...values);
}

/**
 * Converts a backend query-preview response into a normalized frontend dataset.
 * The dataset ID must be provided by the caller (typically the query ID or source ID).
 */
export function previewToDataset(
  id: string,
  name: string,
  preview: DashboardQueryPreviewResponse,
  description?: string,
): NormalizedDataset {
  return {
    id,
    name,
    description: description ?? `Dataset from projection source ${preview.source}.`,
    columns: preview.columns.map((column) => ({
      key: column.key,
      label: column.label,
      type: column.type === 'date' ? 'string' : column.type,
    })),
    rows: preview.rows as Array<Record<string, string | number | boolean | null>>,
    suggestedVisuals: preview.suggested_visuals as NormalizedDataset['suggestedVisuals'],
  };
}

/**
 * Builds the initial dataset registry from projection source auto-hydration results.
 * Each source maps 1-to-1 to a dataset keyed by the source's ID.
 * Derived metric datasets are appended after.
 */
export function buildSourceDatasets(
  results: Array<{ source: DashboardQuerySourceRead; preview: DashboardQueryPreviewResponse }>,
  metrics: DashboardMetricDefinition[] = [],
): Record<DashboardDatasetId, NormalizedDataset> {
  const datasets: Record<DashboardDatasetId, NormalizedDataset> = {};

  for (const { source, preview } of results) {
    datasets[source.id] = previewToDataset(
      source.id,
      source.label,
      preview,
      source.description ?? undefined,
    );
  }

  return appendDerivedMetricDatasets(datasets, metrics);
}

function appendDerivedMetricDatasets(
  datasets: Record<DashboardDatasetId, NormalizedDataset>,
  metricDefinitions: DashboardMetricDefinition[],
): Record<DashboardDatasetId, NormalizedDataset> {
  const derived: Record<string, NormalizedDataset> = {};

  for (const [datasetId, dataset] of Object.entries(datasets)) {
    const numericColumns = dataset.columns.filter((column) => column.type === 'number');
    if (dataset.rows.length === 0) continue;

    const metricRow: Record<string, DashboardPrimitive> = {
      row_count: dataset.rows.length,
    };

    for (const column of numericColumns) {
      const values = dataset.rows
        .map((row) => row[column.key])
        .filter((value): value is number => typeof value === 'number');
      if (values.length === 0) continue;
      metricRow[`${column.key}_sum`] = Number(values.reduce((sum, value) => sum + value, 0).toFixed(2));
      metricRow[`${column.key}_avg`] = Number(average(values).toFixed(2));
      metricRow[`${column.key}_min`] = Math.min(...values);
      metricRow[`${column.key}_max`] = Math.max(...values);
    }

    derived[`${datasetId}__metrics`] = buildDataset(
      `${datasetId}__metrics`,
      `${dataset.name} Metrics`,
      [metricRow],
      ['kpi', 'table'],
      `Auto-generated numeric metrics derived from the ${dataset.name} dataset.`,
    );
  }

  if (metricDefinitions.length > 0) {
    const customMetricRows: Array<Record<string, DashboardPrimitive>> = [];

    for (const metric of metricDefinitions) {
      const sourceDataset = datasets[metric.datasetId];
      if (!sourceDataset) continue;

      const value = computeMetricValue(sourceDataset.rows, metric.aggregation, metric.column);
      const metricRow = {
        metric_id: metric.id,
        metric_name: metric.name,
        metric_label: metric.label,
        dataset_id: metric.datasetId,
        aggregation: metric.aggregation,
        column: metric.column ?? null,
        value,
        format: metric.format ?? 'number',
        color: metric.color ?? null,
      } satisfies Record<string, DashboardPrimitive>;

      customMetricRows.push(metricRow);
      derived[`metric::${metric.id}`] = buildDataset(
        `metric::${metric.id}`,
        metric.label,
        [metricRow],
        ['kpi', 'table'],
        `Reusable custom metric based on the ${sourceDataset.name} dataset.`,
      );
    }

    if (customMetricRows.length > 0) {
      derived.custom_metrics = buildDataset(
        'custom_metrics',
        'Custom Metrics',
        customMetricRows,
        ['kpi', 'bar', 'line', 'area', 'pie', 'table'],
        'All reusable custom metrics in one dataset for comparison across widgets.',
      );
    }
  }

  return {
    ...datasets,
    ...derived,
  };
}

export function getDatasetColumnOptions(dataset?: NormalizedDataset) {
  return (dataset?.columns ?? []).map((column) => ({
    value: column.key,
    label: column.label,
  }));
}

export function createDefaultWidget(
  type: DashboardWidget['type'],
  datasetId: DashboardDatasetId,
  dataset?: NormalizedDataset,
): DashboardWidget {
  const id = `widget-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const numericColumn = dataset?.columns.find((column) => column.type === 'number')?.key;
  const categoricalColumn = dataset?.columns.find((column) => column.type === 'string')?.key;

  if (type === 'kpi') {
    return {
      id,
      title: dataset?.name ?? 'KPI',
      type,
      datasetId,
      config: {
        metricKey: numericColumn ?? dataset?.columns[0]?.key,
        format: 'number',
        palette: 'ocean',
      },
    };
  }

  if (type === 'table') {
    return {
      id,
      title: dataset?.name ?? 'Table',
      type,
      datasetId,
      config: {
        columns: dataset?.columns.slice(0, 5).map((column) => column.key) ?? [],
        rowLimit: 20,
      },
    };
  }

  return {
    id,
    title: dataset?.name ?? 'Chart',
    type,
    datasetId,
    config: {
      xKey: categoricalColumn ?? dataset?.columns[0]?.key,
      yKey: numericColumn ?? dataset?.columns[1]?.key ?? dataset?.columns[0]?.key,
      palette: 'ocean',
      showLegend: true,
      showGrid: true,
      maxItems: 12,
    },
  };
}

export function ensureDashboardDocument(document: DashboardDocument): DashboardDocument {
  return {
    version: document.version ?? 1,
    layout: Array.isArray(document.layout) ? document.layout : [],
    widgets: Array.isArray(document.widgets) ? document.widgets : [],
    metrics: Array.isArray(document.metrics) ? document.metrics : [],
    queries: Array.isArray(document.queries) ? document.queries : [],
    sampleData: document.sampleData ?? {},
  };
}
