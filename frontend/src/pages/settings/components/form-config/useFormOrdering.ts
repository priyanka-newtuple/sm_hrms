import { useMemo, useState } from 'react';
import { formSchemas as formSchemasApi } from '../../../../core/services/api';
import type { FormSchema } from '../../../../core/types';

/** A [normalizedEntityType, forms] pair, forms ordered by display_order. */
export type SchemaGroup = [entityKey: string, schemas: FormSchema[]];

interface UseFormOrderingResult {
  /** Forms grouped by entity type, each group ordered by display_order then name. */
  schemaGroups: SchemaGroup[];
  /** The entity type currently being persisted, for a busy indicator. */
  reorderingEntityType: string | null;
  /** Move a form up (-1) or down (+1) within its group and persist the order. */
  moveSchema: (schema: FormSchema, direction: -1 | 1) => Promise<void>;
}

/**
 * Groups form schemas by entity type and persists manual reordering of
 * `display_order` within each group. Extracted from FormConfigTab so the
 * ordering concern is self-contained (and testable) rather than inlined into
 * an already large component.
 */
export function useFormOrdering(
  schemas: FormSchema[],
  normalizeEntityType: (value: string) => string,
  onReordered: () => Promise<void> | void,
  onError: (message: string) => void,
): UseFormOrderingResult {
  const [reorderingEntityType, setReorderingEntityType] = useState<string | null>(null);

  const schemaGroups = useMemo<SchemaGroup[]>(() => {
    const groups = new Map<string, FormSchema[]>();
    for (const schema of schemas) {
      const key = normalizeEntityType(schema.entity_type);
      const list = groups.get(key);
      if (list) list.push(schema);
      else groups.set(key, [schema]);
    }
    for (const list of groups.values()) {
      list.sort((a, b) => a.display_order - b.display_order || a.name.localeCompare(b.name));
    }
    return [...groups.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [schemas, normalizeEntityType]);

  const moveSchema = async (schema: FormSchema, direction: -1 | 1) => {
    const entityKey = normalizeEntityType(schema.entity_type);
    const group = schemaGroups.find(([key]) => key === entityKey)?.[1] ?? [];
    const idx = group.findIndex((s) => s.id === schema.id);
    const target = idx + direction;
    if (idx < 0 || target < 0 || target >= group.length) return;

    const reordered = group.slice();
    [reordered[idx], reordered[target]] = [reordered[target], reordered[idx]];
    try {
      setReorderingEntityType(entityKey);
      // Persist sequential positions; skip rows whose order is already correct.
      await Promise.all(
        reordered
          .map((s, position) => ({ s, position }))
          .filter(({ s, position }) => s.display_order !== position)
          .map(({ s, position }) => formSchemasApi.reorder(s.schema_key, position)),
      );
      await onReordered();
      window.dispatchEvent(new Event('form-schemas-changed'));
    } catch (e) {
      onError(e instanceof Error ? e.message : 'Failed to reorder forms');
    } finally {
      setReorderingEntityType(null);
    }
  };

  return { schemaGroups, reorderingEntityType, moveSchema };
}
