import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  buildEnrollmentQueryParams,
  fetchEnrollmentSummaryPage,
  type WorkflowEnrollmentFilterParams,
} from '@/core/services/api/workflowEntities';
import { workflowEntityKeys } from '@/core/services/api/queryKeys';

const EMPTY_COUNTS: Record<string, number> = {};

function stateCountsQueryKey(machineName: string, filters: WorkflowEnrollmentFilterParams) {
  return [
    ...workflowEntityKeys.column(machineName, '__state_counts__', filters.thumbnailField),
    filters.anchorEntityId ?? null,
    filters.search ?? '',
    JSON.stringify(filters.fieldFilters ?? {}),
    (filters.assigneeIds ?? []).slice().sort().join(','),
    (filters.excludeStates ?? []).slice().sort().join(','),
  ];
}

/** Board-wide per-state counts, independent of how many pages each column has
 *  loaded — backed by the endpoint's `include=state_counts`, which the
 *  backend already computes as one bounded aggregate query. */
export function useWorkflowStateCounts(machineName: string, filters: WorkflowEnrollmentFilterParams) {
  const queryClient = useQueryClient();
  const queryKey = stateCountsQueryKey(machineName, filters);
  const { data } = useQuery({
    queryKey,
    queryFn: async () => {
      const params = buildEnrollmentQueryParams(machineName, filters);
      params.set('limit', '1');
      params.set('include', 'state_counts');
      const page = await fetchEnrollmentSummaryPage(params);
      return page.stateCounts ?? {};
    },
    enabled: Boolean(machineName),
  });

  const bump = (stateName: string, delta: number) => {
    queryClient.setQueryData<Record<string, number>>(queryKey, (current) => ({
      ...(current ?? {}),
      [stateName]: Math.max(0, (current?.[stateName] ?? 0) + delta),
    }));
  };

  return { counts: data ?? EMPTY_COUNTS, bump };
}
