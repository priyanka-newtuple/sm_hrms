import { useEffect, useMemo } from 'react';

import { usePersistentState } from '@/core/hooks';
import type { WorkflowEntityState } from '@/core/services/api';
import type { FormField, FormSchema } from '@/core/types';
import { getFormFields } from '@/shared/utils/entityForm';
import type { ColumnVisibilityField } from '@/shared/components/ColumnVisibilityMenu';
import { detailFieldsFor } from './components/entityFieldUtils';

/**
 * The structural columns, always offered regardless of entity type.
 *
 * Ids are namespaced because a schema is free to declare a field called
 * `name`, `type`, `state` or `created` — an unprefixed id would produce two
 * columns sharing one TanStack column id, which silently collapses them.
 */
const STANDARD_COLUMNS: ColumnVisibilityField[] = [
  { field: 'std:name', label: 'Name', group: 'standard' },
  { field: 'std:type', label: 'Type', group: 'standard' },
  { field: 'std:state', label: 'State', group: 'standard' },
  { field: 'std:created', label: 'Created', group: 'standard' },
];

/** Shown before the user picks anything: the structural columns only, so a
 *  wide entity type doesn't open as a wall of data columns. */
const DEFAULT_VISIBLE = STANDARD_COLUMNS.map((column) => column.field);

/**
 * Column candidates + persisted visibility for the records list.
 *
 * Data columns are discovered from the rows on screen (schema fields where a
 * schema exists, raw data keys otherwise), so a list mixing entity types
 * offers the union of their fields rather than only the first type's.
 */
export function useEntityColumns(
  entities: WorkflowEntityState[],
  schemaForEntity: (entity: WorkflowEntityState) => FormSchema | null,
  storageKey: string,
) {
  const customFields = useMemo<ColumnVisibilityField[]>(() => {
    const byId = new Map<string, string>();
    for (const entity of entities) {
      for (const field of detailFieldsFor(entity, schemaForEntity(entity))) {
        if (!byId.has(field.id)) byId.set(field.id, field.label);
      }
    }
    return [...byId].map(([field, label]) => ({ field, label, group: 'custom' }));
  }, [entities, schemaForEntity]);

  /** Form field per entity type, so a data cell can format by its declared type. */
  const formFieldsByType = useMemo(() => {
    const byType = new Map<string, Map<string, FormField>>();
    for (const entity of entities) {
      if (byType.has(entity.entity_type)) continue;
      const fields = getFormFields(schemaForEntity(entity));
      byType.set(entity.entity_type, new Map(fields.map((field) => [field.id, field])));
    }
    return byType;
  }, [entities, schemaForEntity]);

  const allFields = useMemo(
    () => [...STANDARD_COLUMNS, ...customFields],
    [customFields],
  );

  const [visibleIds, setVisibleIds] = usePersistentState<string[]>(
    `records-list:cols:v3:${storageKey}`,
    DEFAULT_VISIBLE,
  );

  // Drop ids whose field has since disappeared (schema edit, entity-type
  // filter) and any repeat — a duplicate id would render the same column twice.
  const effectiveIds = useMemo(
    () => [
      ...new Set(visibleIds.filter((id) => allFields.some((field) => field.field === id))),
    ],
    [visibleIds, allFields],
  );

  useEffect(() => {
    if (effectiveIds.length === 0) setVisibleIds(DEFAULT_VISIBLE);
  }, [effectiveIds, setVisibleIds]);

  const visibleCustomFields = useMemo(
    () => customFields.filter((field) => effectiveIds.includes(field.field)),
    [customFields, effectiveIds],
  );

  /** Toggle a column, refusing to hide the last visible one. */
  const toggleField = (field: string) =>
    setVisibleIds((previous) => {
      if (previous.includes(field)) {
        return previous.length > 1 ? previous.filter((id) => id !== field) : previous;
      }
      return [...previous, field];
    });

  const formFieldFor = (entity: WorkflowEntityState, fieldId: string) =>
    formFieldsByType.get(entity.entity_type)?.get(fieldId);

  return { allFields, effectiveIds, visibleCustomFields, toggleField, formFieldFor };
}
