import { useEffect, useMemo } from 'react';
import { usePersistentState, useFormFieldVisibility } from '@/core/hooks';
import type { FormSchema } from '@/core/types';
import type { PipelineListEntity, PipelineViewModel } from '@/shared/types/pipeline';
import { IDENTIFIER_FIELD_KEY, getFormFieldsForSchemas } from '@/shared/utils/entityForm';
import type { ColumnField } from './types';
import { titleCase } from './utils';

function isLegacySchemaMetadataKey(key: string): boolean {
  const normalized = key.replace(/[^a-z0-9]/gi, '').toLowerCase();
  return normalized === 'predefinedreviewrows' || normalized === 'fixedrows' || normalized === 'presetrows';
}

const NO_FIXED_COLUMNS: ColumnField[] = [];

/** Everything a candidate column knows about itself apart from its own id. */
type ColumnFieldMeta = Omit<ColumnField, 'field'>;

interface UseColumnPickerOptions {
  extraColumns?: ColumnField[];
  defaultVisibleFields?: string[];
  fixedColumns?: ColumnField[];
  /** Whether this view renders the columns it is resolving. The persisted
   *  selection is shared per workflow, so a view that only borrows this hook
   *  for its filters (Calendar) must not repair — and thereby overwrite — a
   *  selection belonging to the view that does render columns. */
  ownsColumnSelection?: boolean;
}

/** Column candidate discovery + persisted visibility/order — shared by
 *  `usePipelineList` (Calendar, full-drain) and `usePaginatedPipelineList`
 *  (Table, network-backed). Takes a representative sample of rows purely to
 *  discover which data keys exist; it does not fetch anything itself.
 *
 *  Candidates come from `entitySchemas` — the entity type's *live* form config
 *  (`GET /forms/config`), already fetched by `usePipelineBoardData`. Not the
 *  workflow's embedded `entity_schema` snapshot (`model.schemaFields`), which
 *  is only rewritten when someone re-publishes that workflow in the Funnel
 *  Builder and so goes stale the moment a form gains or loses a field. */
export function useColumnPicker(
  model: PipelineViewModel,
  entitySchemas: FormSchema[],
  sampleEntities: PipelineListEntity[],
  options?: UseColumnPickerOptions,
) {
  const fixedColumns = options?.fixedColumns ?? NO_FIXED_COLUMNS;
  const canViewFormField = useFormFieldVisibility(model.entityType);

  const customFields = useMemo<ColumnField[]>(() => {
    const fields: ColumnField[] = [...(options?.extraColumns ?? [])];
    const seen = new Set([...fixedColumns, ...fields].map((f) => f.field));
    const metaByField = new Map<string, ColumnFieldMeta>();
    // The form config lists every field regardless of role, so columns the
    // actor may not see are dropped here.
    const deniedFields = new Set<string>();
    // `getFormFieldsForSchemas` merges and de-duplicates across every active
    // form on the entity type — one entity type can have several.
    for (const f of getFormFieldsForSchemas(entitySchemas)) {
      if (!canViewFormField(f)) {
        deniedFields.add(f.id);
        continue;
      }
      metaByField.set(f.id, {
        label: f.label || titleCase(f.id),
        type: f.type,
        ...(f.enum_values?.length ? { enum_values: f.enum_values } : {}),
        ...(f.enum_labels?.length ? { enum_labels: f.enum_labels } : {}),
      });
    }
    // Data keys no active form declares (legacy records, agent-written values)
    // stay offerable as columns, labelled from the key itself. Rows arrive
    // already filtered, so this only has to skip fields denied above.
    for (const e of sampleEntities) {
      for (const key of Object.keys(e.data)) {
        if (isLegacySchemaMetadataKey(key)) continue;
        if (deniedFields.has(key)) continue;
        if (!metaByField.has(key)) metaByField.set(key, { label: titleCase(key) });
      }
    }
    metaByField.delete(IDENTIFIER_FIELD_KEY);
    metaByField.delete('due_date');
    for (const [field, meta] of metaByField) {
      if (!seen.has(field)) fields.push({ field, ...meta });
    }
    return fields;
  }, [entitySchemas, sampleEntities, options?.extraColumns, fixedColumns, canViewFormField]);

  const allFields = useMemo<ColumnField[]>(
    () => [...fixedColumns, ...customFields],
    [fixedColumns, customFields],
  );

  const accessorByField = useMemo(() => {
    const map = new Map<string, (e: PipelineListEntity) => unknown>();
    for (const f of customFields) if (f.accessor) map.set(f.field, f.accessor);
    return map;
  }, [customFields]);

  const defaultVisible = useMemo(
    () => [
      ...fixedColumns.map((f) => f.field),
      ...(options?.defaultVisibleFields ?? customFields.slice(0, 1).map((f) => f.field)),
    ],
    [fixedColumns, customFields, options?.defaultVisibleFields],
  );

  const [visibleFieldIds, setVisibleFieldIds] = usePersistentState<string[]>(
    `pipeline-list:cols:v3:${model.machineName}`,
    defaultVisible,
  );

  const effectiveFieldIds = useMemo(
    () => visibleFieldIds.filter((id) => allFields.some((f) => f.field === id)),
    [visibleFieldIds, allFields],
  );

  const ownsColumnSelection = options?.ownsColumnSelection ?? true;
  useEffect(() => {
    // `allFields` empty means the candidates have not resolved yet (schemas in
    // flight, no sample rows) — repairing against an unknown universe would
    // discard a perfectly valid stored selection.
    if (!ownsColumnSelection || allFields.length === 0) return;
    if (effectiveFieldIds.length === 0 && defaultVisible.length > 0) {
      setVisibleFieldIds(defaultVisible);
    }
  }, [ownsColumnSelection, allFields, effectiveFieldIds, defaultVisible, setVisibleFieldIds]);

  const visibleColumns = useMemo(
    () => customFields.filter((f) => effectiveFieldIds.includes(f.field)),
    [customFields, effectiveFieldIds],
  );

  const toggleField = (field: string) =>
    setVisibleFieldIds((prev) => {
      const canHide = !prev.includes(field) || prev.length > 1;
      if (!canHide) return prev;
      return prev.includes(field) ? prev.filter((f) => f !== field) : [...prev, field];
    });

  return { allFields, effectiveFieldIds, visibleColumns, accessorByField, toggleField };
}
