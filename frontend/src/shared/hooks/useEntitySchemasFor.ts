import { useEffect, useState } from 'react';
import { formSchemas } from '@/core/services/api';
import type { FormSchema } from '@/core/types';

function normalizeType(entityType: string): string {
  return entityType.replace(/^ATS\./i, '').trim().toLowerCase();
}

/**
 * All active form schemas attached to an entity type, ordered for display.
 *
 * Several forms may share an entity type; each surfaces as its own tab in the
 * add-entity screen. Sorted by `display_order` (then name) so the configurator
 * controls tab order. Returns an empty array until loaded or when none exist.
 */
export function useEntitySchemasFor(entityType: string | undefined): FormSchema[] {
  return useEntitySchemasForState(entityType).schemas;
}

export function useEntitySchemasForState(entityType: string | undefined): {
  schemas: FormSchema[];
  loading: boolean;
  error: string | null;
} {
  const [result, setResult] = useState<{
    entityType: string | undefined;
    schemas: FormSchema[];
    error: string | null;
  }>({ entityType: undefined, schemas: [], error: null });

  useEffect(() => {
    if (!entityType) return;
    let cancelled = false;
    const target = normalizeType(entityType);
    formSchemas
      .list()
      .then((resp) => {
        if (cancelled) return;
        const matches = resp.items
          .filter((s) => s.is_active && normalizeType(s.entity_type) === target)
          .sort(
            (a, b) =>
              a.display_order - b.display_order || a.name.localeCompare(b.name)
          );
        setResult({ entityType, schemas: matches, error: null });
      })
      .catch((err) => {
        if (!cancelled) {
          setResult({
            entityType,
            schemas: [],
            error: err instanceof Error ? err.message : 'Failed to load forms',
          });
        }
        console.error('Failed to load form schemas for entity type:', entityType, err);
      });
    return () => {
      cancelled = true;
    };
  }, [entityType]);

  if (!entityType) return { schemas: [], loading: false, error: null };
  if (result.entityType !== entityType) return { schemas: [], loading: true, error: null };
  return { schemas: result.schemas, loading: false, error: result.error };
}
