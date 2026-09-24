import { useMemo } from 'react';

import { useStateMachinesList } from '@/core/hooks/useStateMachinesList';
import type {
  EntityField,
  StateMachineDefinition,
} from '@/lib/state-machine/types';

/**
 * Fields each entity type gets from its published workflows' `entity_schema`.
 *
 * These are the Method-Block-contributed fields: they live on the workflow
 * definition, not on any Form, so anything asking "what fields does this entity
 * type have" needs this alongside the Forms list. Pair it with
 * `resolveEntityFormSchemas`, which decides which of the two wins.
 */
export function useWorkflowFieldsByEntityType(): Record<string, EntityField[]> {
  const { data: workflowRecords } = useStateMachinesList();
  return useMemo(() => {
    const byType: Record<string, EntityField[]> = {};
    for (const record of workflowRecords ?? []) {
      if (!record.is_active) continue;
      const definition = record.definition as unknown as StateMachineDefinition | undefined;
      const fields = definition?.entity_schema?.fields;
      const entityType = record.entity_type;
      if (!entityType || !fields?.length) continue;
      // Several workflows can target one entity type; union their fields so a
      // field is offered if any workflow on that type contributes it.
      const existing = byType[entityType] ?? [];
      const seen = new Set(existing.map((f) => f.field));
      byType[entityType] = [...existing, ...fields.filter((f) => !seen.has(f.field))];
    }
    return byType;
  }, [workflowRecords]);
}
