// frontend/src/pages/dashboard/components/QueryBuilderForm.tsx
/**
 * QueryBuilderForm
 *
 * Query-mode widget builder: pick a source, a group-by field, an aggregation,
 * optional field-condition rows, sort + limit, and a viz. Builds a
 * DashboardQueryDefinitionRequest. Used inside WidgetBuilderModal for the
 * 'query' widget kind.
 */
import { useEffect, useState } from 'react';
import { Plus, X } from 'lucide-react';
import { Button, Input, Select } from '../../../core/components';
import { dashboards } from '../../../core/services/api';
import type {
  DashboardQueryDefinitionRequest,
  DashboardQueryFieldRead,
  DashboardQuerySourceRead,
  DashboardViz,
} from '../../../core/types';

const OPS: { value: string; label: string }[] = [
  { value: 'eq', label: '=' },
  { value: 'neq', label: '≠' },
  { value: 'contains', label: 'contains' },
  { value: 'gt', label: '>' },
  { value: 'gte', label: '≥' },
  { value: 'lt', label: '<' },
  { value: 'lte', label: '≤' },
  { value: 'in', label: 'in' },
];

const QUERY_VIZ: { value: DashboardViz; label: string }[] = [
  { value: 'bar', label: 'Bar' },
  { value: 'barh', label: 'Horizontal bar' },
  { value: 'pie', label: 'Pie' },
  { value: 'line', label: 'Line' },
  { value: 'table', label: 'Table' },
];

export interface QueryBuilderFormProps {
  value: DashboardQueryDefinitionRequest | null;
  onChange: (q: DashboardQueryDefinitionRequest) => void;
  viz: DashboardViz;
  onVizChange: (v: DashboardViz) => void;
}

const EMPTY_QUERY: DashboardQueryDefinitionRequest = {
  source: '',
  select: [],
  joins: [],
  filters: [],
  group_by: [],
  aggregations: [],
  sort: [],
  limit: 50,
};

export function QueryBuilderForm({ value, onChange, viz, onVizChange }: QueryBuilderFormProps) {
  const [sources, setSources] = useState<DashboardQuerySourceRead[]>([]);
  const q = value ?? EMPTY_QUERY;

  useEffect(() => {
    let live = true;
    void dashboards.querySources().then((res) => {
      if (live) setSources(res.sources);
    });
    return () => {
      live = false;
    };
  }, []);

  const source = sources.find((s) => s.id === q.source);
  const fields: DashboardQueryFieldRead[] = source?.fields ?? [];
  const groupable = fields.filter((f) => f.groupable);
  const groupField = q.group_by[0] ?? '';
  const aggField = q.aggregations[0]?.field ?? 'entity_id';
  const aggOp = q.aggregations[0]?.op ?? 'count';

  const patch = (next: Partial<DashboardQueryDefinitionRequest>) => onChange({ ...q, ...next });

  const setAggregation = (op: string, fieldKey: string) =>
    patch({ aggregations: [{ field: fieldKey, op: op as 'count', alias: 'value' }] });

  return (
    <div className="space-y-4">
      <Select
        label="Source"
        placeholder={sources.length ? 'Choose a source' : 'Loading…'}
        value={q.source}
        options={sources.map((s) => ({ value: s.id, label: s.label }))}
        onChange={(e) => onChange({ ...EMPTY_QUERY, source: e.target.value })}
      />

      {q.source && (
        <>
          <Select
            label="Group by"
            placeholder="Choose a field"
            value={groupField}
            options={groupable.map((f) => ({ value: f.key, label: f.label }))}
            onChange={(e) =>
              patch({
                group_by: e.target.value ? [e.target.value] : [],
                aggregations: q.aggregations.length
                  ? q.aggregations
                  : [{ field: 'entity_id', op: 'count', alias: 'value' }],
              })
            }
          />

          <div className="grid grid-cols-2 gap-3">
            <Select
              label="Aggregation"
              value={aggOp}
              options={[
                { value: 'count', label: 'Count' },
                { value: 'sum', label: 'Sum' },
                { value: 'avg', label: 'Average' },
                { value: 'min', label: 'Min' },
                { value: 'max', label: 'Max' },
              ]}
              onChange={(e) => setAggregation(e.target.value, aggOp === 'count' ? 'entity_id' : aggField)}
            />
            {aggOp !== 'count' && (
              <Select
                label="Of field"
                value={aggField}
                options={fields
                  .filter((f) => f.aggregatable)
                  .map((f) => ({ value: f.key, label: f.label }))}
                onChange={(e) => setAggregation(aggOp, e.target.value)}
              />
            )}
          </div>

          <div className="space-y-1.5">
            <span className="text-sm font-medium text-foreground">Conditions</span>
            {q.filters.map((f, i) => (
              <div key={i} className="flex items-end gap-2">
                <Select
                  label=""
                  value={f.field}
                  options={fields
                    .filter((x) => x.filterable)
                    .map((x) => ({ value: x.key, label: x.label }))}
                  onChange={(e) => {
                    const filters = [...q.filters];
                    filters[i] = { ...filters[i], field: e.target.value };
                    patch({ filters });
                  }}
                />
                <Select
                  label=""
                  value={f.op}
                  options={OPS}
                  onChange={(e) => {
                    const filters = [...q.filters];
                    filters[i] = { ...filters[i], op: e.target.value as 'eq' };
                    patch({ filters });
                  }}
                />
                <Input
                  label=""
                  value={String(f.value ?? '')}
                  onChange={(e) => {
                    const filters = [...q.filters];
                    filters[i] = { ...filters[i], value: e.target.value };
                    patch({ filters });
                  }}
                />
                <button
                  type="button"
                  aria-label="Remove condition"
                  className="mb-2 text-muted-foreground hover:text-destructive"
                  onClick={() => patch({ filters: q.filters.filter((_, j) => j !== i) })}
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            ))}
            <Button
              variant="ghost"
              size="sm"
              onClick={() =>
                patch({
                  filters: [
                    ...q.filters,
                    { field: groupable[0]?.key ?? 'current_state', op: 'eq', value: '' },
                  ],
                })
              }
            >
              <Plus className="h-4 w-4" strokeWidth={1.5} />
              Add condition
            </Button>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Limit"
              type="number"
              value={String(q.limit)}
              onChange={(e) => patch({ limit: Math.max(1, Number(e.target.value) || 50) })}
            />
            <Select
              label="Sort"
              value={q.sort[0]?.direction ?? ''}
              options={[
                { value: '', label: 'None' },
                { value: 'desc', label: 'Highest first' },
                { value: 'asc', label: 'Lowest first' },
              ]}
              onChange={(e) =>
                patch({
                  sort: e.target.value
                    ? [{ field: 'value', direction: e.target.value as 'asc' | 'desc' }]
                    : [],
                })
              }
            />
          </div>

          <div className="space-y-1.5">
            <span className="text-sm font-medium text-foreground">Visualization</span>
            <div className="flex flex-wrap gap-2">
              {QUERY_VIZ.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => onVizChange(opt.value)}
                  className={
                    viz === opt.value
                      ? 'rounded-full border border-cobalt bg-cobalt/10 px-3 py-1 text-sm font-medium text-cobalt'
                      : 'rounded-full border border-border px-3 py-1 text-sm text-muted-foreground hover:bg-muted'
                  }
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
