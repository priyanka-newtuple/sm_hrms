import { useCallback, useEffect, useState } from 'react';
import { transitions } from '@/core/services/api';
import type { AvailableTransition } from '@/core/types';

interface UseAvailableTransitionsResult {
  available: AvailableTransition[];
  loading: boolean;
  error: boolean;
  refetch: () => Promise<void>;
  execute: (trigger: string) => Promise<void>;
}

export function useAvailableTransitions(
  entityId: string | undefined,
  /** Changing this re-fetches available transitions (e.g. when entity data/state updates). */
  refreshKey?: unknown,
  prefetched?: AvailableTransition[],
  workflowId?: string,
): UseAvailableTransitionsResult {
  const [available, setAvailable] = useState<AvailableTransition[]>(prefetched ?? []);
  const [loading, setLoading] = useState(Boolean(entityId) && prefetched === undefined);
  const [error, setError] = useState(false);

  const refetch = useCallback(async () => {
    if (prefetched !== undefined) {
      setAvailable(prefetched);
      setLoading(false);
      setError(false);
      return;
    }
    if (!entityId) {
      setAvailable([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(false);
    try {
      const resp = await transitions.getAvailable(entityId, workflowId);
      setAvailable(resp.available_transitions);
    } catch {
      setAvailable([]);
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [entityId, refreshKey, prefetched, workflowId]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  const execute = useCallback(
    async (trigger: string) => {
      if (!entityId) return;
      await transitions.execute(entityId, {
        entity_id: entityId,
        ...(workflowId ? { workflow_id: workflowId } : {}),
        trigger,
        idempotency_key: `${entityId}-${workflowId ?? 'primary'}-${trigger}-${Date.now()}`,
      });
    },
    [entityId, workflowId],
  );

  return { available, loading, error, refetch, execute };
}
