import { useCallback, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { workflowEntities } from '@/core/services/api';
import type { WorkflowEntityState } from '@/core/services/api';
import { workflowEntityKeys } from '@/core/services/api/queryKeys';
import { useGlobalEntityFilter } from '@/core/contexts/GlobalEntityFilterContext';

// Stable reference for the no-data case — `data ?? []` would otherwise
// allocate a new array every render while the query is pending, which
// breaks every downstream consumer that compares `entities` by reference
// (e.g. a "reset filtered rows only when entities change" guard) and can
// drive React into a render loop.
const EMPTY_ENTITIES: WorkflowEntityState[] = [];

interface UpdateEntityPayload {
  data?: Record<string, unknown>;
  due_date?: string | null;
  schema_fields?: Array<Record<string, unknown>>;
}

interface UseWorkflowEntitiesResult {
  entities: WorkflowEntityState[];
  loading: boolean;
  refetch: () => Promise<void>;
  patchEntityData: (entityId: string, data: Record<string, unknown>) => void;
  patchEntityState: (entityId: string, stateId: string, workflowId?: string) => void;
  updateEntity: (entityId: string, payload: UpdateEntityPayload) => Promise<void>;
}

/**
 * Backed by a shared React Query cache keyed on (machineName, thumbnailField,
 * anchorEntityId). Several independent consumers (pipeline board, sidebar
 * badge count, other skin pages) read the same workflow's entities — sharing
 * the cache means a transition/update triggered from any one of them
 * (invalidated centrally in the transitions/workflowEntities API modules)
 * refreshes all of them together, instead of each hook instance drifting out
 * of sync with its own local state.
 */
export function useWorkflowEntities(
  machineName: string | undefined,
  thumbnailField?: string,
  options?: {
    refetchIntervalMs?: number;
    stateNames?: string[];
    summaryFields?: string[];
    /** Defaults to true. Set false to skip fetching entirely (e.g. a
     *  Calendar tab that isn't currently active) without unmounting the
     *  hook — flips back to fetching the moment it becomes true again. */
    enabled?: boolean;
  },
): UseWorkflowEntitiesResult {
  const { activeAnchorEntityId } = useGlobalEntityFilter();
  const queryClient = useQueryClient();
  const queryKey = useMemo(
    () => [
      ...workflowEntityKeys.list(machineName ?? '', thumbnailField),
      activeAnchorEntityId ?? null,
      (options?.stateNames ?? []).join(','),
      (options?.summaryFields ?? []).join(','),
    ],
    [machineName, thumbnailField, activeAnchorEntityId, options?.stateNames, options?.summaryFields],
  );

  const { data, isLoading, refetch: refetchQuery } = useQuery({
    queryKey,
    queryFn: async () => {
      const states = options?.stateNames ?? [];
      const params = {
        thumbnailField,
        anchorEntityId: activeAnchorEntityId,
        summaryFields: options?.summaryFields,
      };
      if (states.length === 0) return workflowEntities.list(machineName, undefined, params);
      const pages = await Promise.all(
        states.map((state) => workflowEntities.list(machineName, state, params)),
      );
      return pages.flat();
    },
    enabled: Boolean(machineName) && (options?.enabled ?? true),
    // Opt-in only (undefined = no polling, preserving default behavior for
    // every existing consumer/skin) — a board with many simultaneous users
    // claiming/updating the same entities needs to notice those changes
    // without waiting for its own next user-triggered action.
    refetchInterval: options?.refetchIntervalMs,
    // Pauses the interval while the tab is hidden/unfocused.
    refetchIntervalInBackground: false,
    // The app-wide default disables this (see core/queryClient.ts) to avoid
    // spurious refetches on unrelated pages when the user alt-tabs back in.
    // Polling consumers need the opposite: coming back to the board tab
    // should refresh immediately, not wait up to a full interval tick.
    refetchOnWindowFocus: options?.refetchIntervalMs ? true : undefined,
  });

  const entities = data ?? EMPTY_ENTITIES;

  const refetch = useCallback(async () => {
    if (!machineName) return;
    await refetchQuery();
  }, [machineName, refetchQuery]);

  const patchEntityData = useCallback(
    (entityId: string, data: Record<string, unknown>) => {
      if (!machineName) return;
      queryClient.setQueriesData<WorkflowEntityState[]>(
        { queryKey: workflowEntityKeys.all() },
        (prev) => prev?.map((e) => (e.entity_id === entityId ? { ...e, data } : e)) ?? prev,
      );
    },
    [machineName, queryClient],
  );

  const patchEntityState = useCallback(
    (entityId: string, stateId: string, workflowId?: string) => {
      if (!machineName) return;
      queryClient.setQueriesData<WorkflowEntityState[]>(
        { queryKey: workflowEntityKeys.all() },
        (prev) =>
          prev?.map((e) => (
            e.entity_id === entityId && (!workflowId || e.workflow_id === workflowId)
              ? { ...e, current_state: stateId }
              : e
          )) ?? prev,
      );
    },
    [machineName, queryClient],
  );

  const updateEntity = useCallback(async (entityId: string, payload: UpdateEntityPayload) => {
    await workflowEntities.update(entityId, payload);
  }, []);

  return { entities, loading: isLoading, refetch, patchEntityData, patchEntityState, updateEntity };
}
