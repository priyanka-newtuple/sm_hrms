import { useQuery, useQueryClient, type UseQueryResult } from '@tanstack/react-query';
import { stateMachines } from '../services/api';
import type { StateMachineRecord } from '../types';

/**
 * Every consumer that needs the full state-machine list (SkinContext,
 * useWorkflows, useFunnelList) reads through this one query key, so
 * simultaneous mounts share a single in-flight request and cached result
 * instead of each firing its own /workflow-state-machines?scope=all call.
 */
export const STATE_MACHINES_LIST_QUERY_KEY = ['stateMachines', 'list'] as const;

export function useStateMachinesList(enabled: boolean = true): UseQueryResult<StateMachineRecord[]> {
  return useQuery({
    queryKey: STATE_MACHINES_LIST_QUERY_KEY,
    queryFn: () => stateMachines.list(),
    enabled,
  });
}

/** Forces every mounted consumer of {@link useStateMachinesList} to refetch. */
export function useInvalidateStateMachinesList(): () => Promise<void> {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: STATE_MACHINES_LIST_QUERY_KEY });
}
