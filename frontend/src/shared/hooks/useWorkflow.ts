import { useEffect, useState } from 'react';
import { stateMachines } from '@/core/services/api';
import type { StateMachineRecord } from '@/core/types';

interface UseWorkflowResult {
  workflow: StateMachineRecord | null;
  loading: boolean;
  error: string | null;
}

export function useWorkflow(id: string | undefined): UseWorkflowResult {
  const [workflow, setWorkflow] = useState<StateMachineRecord | null>(null);
  const [loading, setLoading] = useState(Boolean(id));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) {
      setWorkflow(null);
      setError(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    stateMachines
      .getById(id)
      .then(async (record) => {
        // TODO: Move active-row resolution behind an explicit pipeline-only
        // option so historical workflow consumers can load exact row ids.
        if (!record.is_active || record.version === 0) {
          return stateMachines.getActive(record.machine_name).catch(() => record);
        }
        return record;
      })
      .then((record) => {
        if (!cancelled) {
          setWorkflow(record);
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setWorkflow(null);
          setError(e instanceof Error ? e.message : 'Failed to load workflow');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  return { workflow, loading, error };
}
