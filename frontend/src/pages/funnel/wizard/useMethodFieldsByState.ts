import { useEffect, useMemo, useState } from 'react';
import { fieldLibrary, methodLibrary } from '@/core/services/api';
import type { FieldTypeOption, MethodVersionField } from '@/core/types';
import type { EntityField, StateNode } from '@/lib/state-machine/types';
import {
  buildFieldTypeCatalogue,
  fieldsForMethod,
  methodIdsFromStates,
  resolveFieldsByState,
  type FieldTypeCatalogue,
} from '@/lib/state-machine/methodFields';

/**
 * React-hook wrapper around the shared, framework-agnostic resolution logic
 * in `lib/state-machine/methodFields.ts`. This hook owns the data fetching
 * (fieldLibrary.listFieldTypes(), methodLibrary.get() per method); the
 * actual per-state scoping is delegated to `resolveFieldsByState` so any
 * other caller — e.g. a skin's own designer UI, which already imports
 * shared types from `lib/state-machine/` — can reuse the exact same
 * computation against its own fetched data, without needing this hook or
 * React at all. See methodFields.ts's file comment for the full rationale.
 *
 * Known limitation: methodLibrary.get() has no version-specific fetch (there
 * is no frontend-facing endpoint for one — only the backend's own publish-time
 * resolution reads a specific pinned version via list_version_fields). A state
 * whose method_refs pins an older version previews that method's CURRENT
 * fields, not necessarily the exact historical version. This matches the
 * same simplification already documented on the backend's
 * get_method_with_fields_for_actor.
 */
export function useMethodFieldsByState(states: StateNode[]): {
  fieldsByState: Record<string, EntityField[]>;
  loading: boolean;
} {
  const [fieldsByMethod, setFieldsByMethod] = useState<Record<string, EntityField[]>>({});
  const [loading, setLoading] = useState(false);

  const methodIds = useMemo(() => methodIdsFromStates(states), [states]);
  const methodIdsKey = methodIds.join(',');

  useEffect(() => {
    if (methodIds.length === 0) {
      setFieldsByMethod({});
      return;
    }
    let cancelled = false;
    setLoading(true);
    Promise.all([
      fieldLibrary.listFieldTypes().catch(() => ({ organization_id: '', items: [] as FieldTypeOption[] })),
      Promise.all(
        methodIds.map((id) =>
          methodLibrary
            .get(id)
            .then((m) => [id, m.fields] as const)
            .catch(() => [id, [] as MethodVersionField[]] as const),
        ),
      ),
    ]).then(([catalogueResponse, methodEntries]) => {
      if (cancelled) return;
      const catalogue: FieldTypeCatalogue = buildFieldTypeCatalogue(catalogueResponse.items);
      const nextFieldsByMethod: Record<string, EntityField[]> = {};
      for (const [methodId, fields] of methodEntries) {
        nextFieldsByMethod[methodId] = fieldsForMethod(fields, catalogue);
      }
      setFieldsByMethod(nextFieldsByMethod);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
    // methodIds is derived from methodIdsKey; re-running on the joined key
    // avoids refetching on every render when the array identity changes but
    // its contents don't.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [methodIdsKey]);

  const fieldsByState = useMemo(
    () => resolveFieldsByState(states, fieldsByMethod),
    [states, fieldsByMethod],
  );

  return { fieldsByState, loading };
}
