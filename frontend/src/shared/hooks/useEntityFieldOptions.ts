import { useEffect, useState } from 'react';

import { formSchemas } from '@/core/services/api';
import { getFormFields } from '@/shared/utils/entityForm';

/**
 * Field-name options for an entity type, sourced from its form schemas (the same source the
 * workflow editor uses). Returns the unique entity field keys (FormField.id).
 */
export function useEntityFieldOptions(entityType: string | undefined): string[] {
  const [fields, setFields] = useState<string[]>([]);

  useEffect(() => {
    if (!entityType || entityType === 'entity') {
      setFields([]);
      return;
    }
    let cancelled = false;
    formSchemas
      .list(entityType)
      .then((resp) => {
        if (cancelled) return;
        const seen = new Set<string>();
        const ids: string[] = [];
        for (const field of resp.items.flatMap((schema) => getFormFields(schema))) {
          if (!seen.has(field.id)) {
            seen.add(field.id);
            ids.push(field.id);
          }
        }
        setFields(ids);
      })
      .catch((err) => {
        if (!cancelled) {
          console.warn('Failed to load entity field options', err);
          setFields([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [entityType]);

  return fields;
}

export interface EntityFieldOptionsForTypes {
  /** Union of field ids across all requested entity types. */
  fields: string[];
  /** Field ids grouped per entity type, in the requested order. */
  byType: Array<{ type: string; fields: string[] }>;
  /** field id → requested entity types that do NOT define it. */
  missingByField: Record<string, string[]>;
  /** Set when field options failed to load for one or more types. */
  error: string | null;
}

/** Field-name options across multiple entity types, with per-field missing-type info. */
export function useEntityFieldOptionsForTypes(entityTypes: string[]): EntityFieldOptionsForTypes {
  const key = entityTypes.filter((t) => t && t !== 'entity').join('|');
  const [result, setResult] = useState<EntityFieldOptionsForTypes>({
    fields: [],
    byType: [],
    missingByField: {},
    error: null,
  });

  useEffect(() => {
    const types = key ? key.split('|') : [];
    if (!types.length) {
      setResult({ fields: [], byType: [], missingByField: {}, error: null });
      return;
    }
    let cancelled = false;
    Promise.all(
      types.map((type) =>
        formSchemas
          .list(type)
          .then((resp) => {
            const ids = new Set<string>();
            for (const field of resp.items.flatMap((schema) => getFormFields(schema))) {
              ids.add(field.id);
            }
            return { type, ids, failed: false };
          })
          .catch((err) => {
            console.warn(`Failed to load entity field options for ${type}`, err);
            return { type, ids: new Set<string>(), failed: true };
          }),
      ),
    ).then((results) => {
      if (cancelled) return;
      // A failed type must not count as "missing every field" — exclude it from the
      // missing-type computation and surface the failure instead.
      const loaded = results.filter((r) => !r.failed);
      const failed = results.filter((r) => r.failed).map((r) => r.type);
      const fields: string[] = [];
      const seen = new Set<string>();
      for (const { ids } of loaded) {
        for (const id of ids) {
          if (!seen.has(id)) {
            seen.add(id);
            fields.push(id);
          }
        }
      }
      const missingByField: Record<string, string[]> = {};
      for (const id of fields) {
        const missing = loaded.filter(({ ids }) => !ids.has(id)).map(({ type }) => type);
        if (missing.length) missingByField[id] = missing;
      }
      setResult({
        fields,
        byType: loaded.map(({ type, ids }) => ({ type, fields: [...ids] })),
        missingByField,
        error: failed.length ? `Failed to load fields for: ${failed.join(', ')}` : null,
      });
    });
    return () => {
      cancelled = true;
    };
  }, [key]);

  return result;
}
