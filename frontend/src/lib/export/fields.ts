import type { PipelineListEntity, PipelineSchemaField } from '@/shared/types/pipeline';
import { humanize } from '@/shared/utils/labels';
import type { ExportField, ExportFormat, ExportRow } from './types';

const DATA_PREFIX = 'data.';

/** Canonical display order for well-known system fields. Unknown system keys
 *  are appended alphabetically after these. */
const SYSTEM_ORDER = [
  'entity_id',
  'current_state',
  'current_state_description',
  'state_entered_at',
  'created_at',
  'updated_at',
  'last_transition_at',
  'sla_due_at',
  'owner_id',
  'owner_name',
  'machine_name',
  'entity_type',
];

const SYSTEM_LABELS: Record<string, string> = {
  entity_id: 'Entity ID',
  current_state: 'Current State',
  current_state_description: 'State Description',
  state_entered_at: 'State Entered At',
  created_at: 'Created At',
  updated_at: 'Updated At',
  last_transition_at: 'Last Transition At',
  sla_due_at: 'SLA Due At',
  owner_id: 'Owner ID',
  owner_name: 'Owner',
  machine_name: 'Workflow',
  entity_type: 'Entity Type',
};

/** Core system fields selected by default. */
const DEFAULT_SYSTEM_KEYS = ['entity_id', 'current_state', 'created_at'];

/** Platform-wide field-key → label formatter. */
const titleCase = humanize;

function isEmpty(value: unknown): boolean {
  if (value === null || value === undefined || value === '') return true;
  if (Array.isArray(value)) return value.length === 0;
  if (typeof value === 'object') return Object.keys(value as object).length === 0;
  return false;
}

/**
 * Resolve display labels for the given fields, de-duplicating collisions so
 * every column header is unique. Two fields that share a label (e.g. a system
 * key and a data key that title-case to the same text) would otherwise
 * overwrite each other as JSON keys. Order matches the input fields.
 */
export function resolveFieldLabels(fields: ExportField[]): string[] {
  const used = new Set<string>();
  return fields.map((f) => {
    let label = f.label;
    let n = 1;
    while (used.has(label)) label = `${f.label} (${++n})`;
    used.add(label);
    return label;
  });
}

/** Derive the full ordered set of selectable fields from the rows. */
export function deriveExportFields(
  entities: PipelineListEntity[],
  schemaFields: PipelineSchemaField[],
): ExportField[] {
  const total = entities.length;

  // --- System fields: every top-level key except `data`. ---
  const systemKeys = new Set<string>();
  for (const e of entities) {
    for (const k of Object.keys(e)) {
      if (k !== 'data') systemKeys.add(k);
    }
  }
  const orderedSystemKeys = [
    ...SYSTEM_ORDER.filter((k) => systemKeys.has(k)),
    ...[...systemKeys].filter((k) => !SYSTEM_ORDER.includes(k)).sort(),
  ];
  const systemFields: ExportField[] = orderedSystemKeys.map((key) => ({
    key,
    label: SYSTEM_LABELS[key] ?? titleCase(key),
    group: 'system',
    fillCount: entities.filter((e) => !isEmpty((e as unknown as Record<string, unknown>)[key]))
      .length,
    totalCount: total,
  }));

  // --- Data fields: union of keys across all entity.data objects. ---
  const schemaLabelByField = new Map(schemaFields.map((f) => [f.field, f.label]));
  const dataKeys = new Set<string>(schemaFields.map((f) => f.field));
  for (const e of entities) {
    for (const k of Object.keys(e.data ?? {})) dataKeys.add(k);
  }
  const dataFields: ExportField[] = [...dataKeys]
    .map((k) => ({
      key: `${DATA_PREFIX}${k}`,
      label: schemaLabelByField.get(k) ?? titleCase(k),
      group: 'data' as const,
      fillCount: entities.filter((e) => !isEmpty((e.data ?? {})[k])).length,
      totalCount: total,
    }))
    // Most-populated first, then alphabetical by label for stable ordering.
    .sort((a, b) => b.fillCount - a.fillCount || a.label.localeCompare(b.label));

  return [...systemFields, ...dataFields];
}

function valueForField(entity: PipelineListEntity, field: ExportField): unknown {
  if (field.key.startsWith(DATA_PREFIX)) {
    return (entity.data ?? {})[field.key.slice(DATA_PREFIX.length)];
  }
  return (entity as unknown as Record<string, unknown>)[field.key];
}

/** Flatten entities into rows keyed by `ExportField.key`. */
export function buildExportRows(
  entities: PipelineListEntity[],
  fields: ExportField[],
): ExportRow[] {
  return entities.map((e) => {
    const row: ExportRow = {};
    for (const f of fields) row[f.key] = valueForField(e, f);
    return row;
  });
}

/** Default selection: core system fields + every data field that has data. */
export function defaultSelectedKeys(fields: ExportField[]): Set<string> {
  const selected = new Set<string>();
  for (const f of fields) {
    if (f.group === 'system' && DEFAULT_SYSTEM_KEYS.includes(f.key)) selected.add(f.key);
    if (f.group === 'data' && f.fillCount > 0) selected.add(f.key);
  }
  return selected;
}

/** Filter the derived field list to the selection, preserving derived order. */
export function orderSelectedFields(
  fields: ExportField[],
  selected: Set<string>,
): ExportField[] {
  return fields.filter((f) => selected.has(f.key));
}

/** Build a download filename like `my-workflow-2026-06-18.csv`. */
export function buildExportFilename(workflowName: string, format: ExportFormat): string {
  const slug =
    workflowName
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '') || 'export';
  const date = new Date().toISOString().slice(0, 10);
  return `${slug}-${date}.${format}`;
}
