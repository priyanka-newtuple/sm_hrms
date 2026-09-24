import { useEffect, useMemo } from 'react';
import { STATE_MACHINES_CHANGED_EVENT } from '@/core/events';
import { useStateMachinesList, useInvalidateStateMachinesList } from '@/core/hooks/useStateMachinesList';
import { humanize } from '@/shared/utils/labels';
import type { StateMachineRecord } from '@/core/types';

export interface Workflow {
  id: string;
  slug: string;
  label: string;
  isActive: boolean;
  entityType: string;
}

interface UseWorkflowsResult {
  workflows: Workflow[];
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}


function toWorkflows(records: StateMachineRecord[]): Workflow[] {
  const latest = new Map<string, StateMachineRecord>();
  for (const rec of records) {
    const existing = latest.get(rec.machine_name);
    if (!existing || rec.version > existing.version) {
      latest.set(rec.machine_name, rec);
    }
  }
  return Array.from(latest.values())
    .map((rec) => {
      const def = rec.definition as { name?: string };
      return {
        id: rec.id ?? rec.machine_name,
        slug: rec.machine_name,
        label: def?.name ?? humanize(rec.machine_name),
        isActive: rec.is_active,
        entityType: rec.entity_type,
      };
    })
    .sort((a, b) => a.label.localeCompare(b.label));
}

export function useWorkflows(): UseWorkflowsResult {
  const { data, isLoading, error, refetch } = useStateMachinesList();
  const invalidate = useInvalidateStateMachinesList();

  useEffect(() => {
    window.addEventListener(STATE_MACHINES_CHANGED_EVENT, invalidate);
    return () => window.removeEventListener(STATE_MACHINES_CHANGED_EVENT, invalidate);
  }, [invalidate]);

  const workflows = useMemo(() => toWorkflows(data ?? []), [data]);

  return {
    workflows,
    loading: isLoading,
    error: error ? (error instanceof Error ? error.message : 'Failed to load workflows') : null,
    refetch: async () => {
      await refetch();
    },
  };
}
