import { useCallback, useMemo, useState } from 'react';
import { toast } from 'sonner';
import type { AvailableTransition } from '@/core/types';
import { transitions, workflowEntities } from '@/core/services/api';
import { getApiErrorMessage } from '@/core/services/api/client';
import type { PipelineTransitionEdge } from '@/shared/types/pipeline';

const BULK_MUTATION_CONCURRENCY = 5;

export interface BulkActionEntity {
  entity_id: string;
  workflow_id?: string;
  current_state: string;
  transition_options?: AvailableTransition[];
}

interface UseBulkEntityActionsOptions {
  onCommitted: () => void;
  /** Changing scope hides stale selections without a render-time state reset. */
  scopeKey?: string;
}

async function settleWithConcurrency<T>(
  items: T[],
  worker: (item: T) => Promise<unknown>,
): Promise<PromiseSettledResult<unknown>[]> {
  const results: PromiseSettledResult<unknown>[] = new Array(items.length);
  let nextIndex = 0;

  async function runWorker(): Promise<void> {
    while (nextIndex < items.length) {
      const index = nextIndex;
      nextIndex += 1;
      try {
        results[index] = { status: 'fulfilled', value: await worker(items[index]) };
      } catch (reason) {
        results[index] = { status: 'rejected', reason };
      }
    }
  }

  await Promise.all(
    Array.from(
      { length: Math.min(BULK_MUTATION_CONCURRENCY, items.length) },
      () => runWorker(),
    ),
  );
  return results;
}

interface SelectionState {
  scopeKey: string;
  entities: Map<string, BulkActionEntity>;
}

export function useBulkEntityActions({ onCommitted, scopeKey = '' }: UseBulkEntityActionsOptions) {
  const [selection, setSelection] = useState<SelectionState>({
    scopeKey,
    entities: new Map(),
  });
  const [busy, setBusy] = useState(false);
  const selectedById = useMemo(
    () => selection.scopeKey === scopeKey ? selection.entities : new Map<string, BulkActionEntity>(),
    [scopeKey, selection],
  );
  const selected = useMemo(() => Array.from(selectedById.values()), [selectedById]);
  const selectedIds = useMemo(() => new Set(selectedById.keys()), [selectedById]);

  const setSelected = useCallback((entity: BulkActionEntity, checked: boolean) => {
    setSelection((current) => {
      const next = new Map(current.scopeKey === scopeKey ? current.entities : []);
      if (checked) next.set(entity.entity_id, entity);
      else next.delete(entity.entity_id);
      return { scopeKey, entities: next };
    });
  }, [scopeKey]);

  const clear = useCallback(
    () => setSelection({ scopeKey, entities: new Map() }),
    [scopeKey],
  );

  const execute = useCallback(async (
    worker: (entity: BulkActionEntity) => Promise<unknown>,
    successVerb: string,
    failureNoun: string,
  ) => {
    const targets = Array.from(selectedById.values());
    if (!targets.length) return;
    setBusy(true);
    try {
      const results = await settleWithConcurrency(targets, worker);
      const failedIds = new Set(
        targets
          .filter((_, index) => results[index].status === 'rejected')
          .map((entity) => entity.entity_id),
      );
      const succeeded = targets.length - failedIds.size;
      setSelection({
        scopeKey,
        entities: new Map(
          targets
            .filter((entity) => failedIds.has(entity.entity_id))
            .map((entity) => [entity.entity_id, entity]),
        ),
      });
      onCommitted();
      if (succeeded) {
        toast.success(`${succeeded} ${succeeded === 1 ? 'entity' : 'entities'} ${successVerb}`);
      }
      if (failedIds.size) {
        const firstFailure = results.find((result) => result.status === 'rejected');
        toast.error(`${failedIds.size} ${failedIds.size === 1 ? failureNoun : `${failureNoun}s`} failed`, {
          description: firstFailure?.status === 'rejected'
            ? getApiErrorMessage(firstFailure.reason)
            : undefined,
        });
      }
    } finally {
      setBusy(false);
    }
  }, [onCommitted, scopeKey, selectedById]);

  const transition = useCallback(async (edge: PipelineTransitionEdge) => {
    await execute(
      (entity) => transitions.execute(entity.entity_id, {
        entity_id: entity.entity_id,
        ...(entity.workflow_id ? { workflow_id: entity.workflow_id } : {}),
        trigger: edge.trigger,
        idempotency_key: `${entity.entity_id}-${entity.workflow_id ?? 'primary'}-${edge.trigger}-${Date.now()}`,
      }),
      'transitioned',
      'transition',
    );
  }, [execute]);

  const remove = useCallback(async () => {
    await execute(
      (entity) => workflowEntities.delete(entity.entity_id),
      'deleted',
      'deletion',
    );
  }, [execute]);

  return { selected, selectedIds, busy, setSelected, clear, transition, remove };
}
