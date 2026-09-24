import { useCallback, useState } from 'react';
import { entityRelations, entityTypes as entityTypesApi } from '../services/api';
import type { RelationDeclaration } from '../types';

export type SourceRecordOption = { entity_id: string; label: string };

export type SourcePicker = {
  declaration: RelationDeclaration;
  providerName: string;
};

function recordLabel(data: Record<string, unknown>, entityId: string): string {
  // 'identifier' is the platform-wide unique-name key on entity data.
  const identifier = data['identifier'];
  if (typeof identifier === 'string' && identifier.trim()) return identifier.trim();
  for (const value of Object.values(data)) {
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return entityId.slice(0, 8);
}

/** Server-side search for source records of a provider type — top `limit` matches. */
export async function searchSourceRecords(
  providerName: string,
  search: string,
  limit = 20
): Promise<SourceRecordOption[]> {
  const res = await entityRelations.listRecordsOfType(providerName, search, limit);
  return (res.items ?? []).map((r) => ({
    entity_id: r.entity_id,
    label: recordLabel(r.data ?? {}, r.entity_id),
  }));
}

/**
 * Source-record link pickers for entity creation: one picker per relation
 * declaration targeting the entity type (REFERENCE = required, SNAPSHOT =
 * optional). Call `load(entityTypeName)` when the create dialog opens and
 * `reset()` when it closes; include `sourceEntityIds` in the create payload.
 * Record options are searched server-side per picker (see searchSourceRecords).
 */
export function useSourcePickers() {
  const [pickers, setPickers] = useState<SourcePicker[]>([]);
  const [selections, setSelections] = useState<Record<string, string>>({});

  const load = useCallback(async (entityTypeName: string) => {
    setSelections({});
    try {
      const typesRes = await entityTypesApi.list();
      const nameById = new Map<string, string>();
      let targetId: string | null = null;
      for (const t of typesRes.items ?? []) {
        const id = t.entity_type_id ?? t.id;
        nameById.set(id, t.name);
        if (t.name.toLowerCase() === entityTypeName.toLowerCase()) targetId = id;
      }
      if (!targetId) {
        setPickers([]);
        return;
      }
      const decls = await entityRelations.listDeclarations(targetId, 'to');
      setPickers(
        (decls.items ?? []).map((declaration) => ({
          declaration,
          providerName: nameById.get(declaration.from_entity_type_id) ?? '',
        }))
      );
    } catch (err) {
      // Degrade to no pickers — the backend still enforces REFERENCE links on
      // submit — but keep the failure diagnosable.
      console.error('Failed to load relation declarations:', err);
      setPickers([]);
    }
  }, []);

  const reset = useCallback(() => {
    setPickers([]);
    setSelections({});
  }, []);

  const setSelection = useCallback((defId: string, entityId: string) => {
    setSelections((prev) => ({ ...prev, [defId]: entityId }));
  }, []);

  const missingRequired =
    pickers.find(
      (p) =>
        p.declaration.relation_type === 'REFERENCE' &&
        !selections[p.declaration.relation_def_id]
    ) ?? null;

  const sourceEntityIds = Object.values(selections).filter(Boolean);

  return { pickers, selections, load, reset, setSelection, missingRequired, sourceEntityIds };
}
