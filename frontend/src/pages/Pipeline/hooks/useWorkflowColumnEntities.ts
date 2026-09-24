import { useInfiniteQuery, type QueryClient, type QueryKey } from '@tanstack/react-query';
import {
  buildEnrollmentQueryParams,
  fetchEnrollmentSummaryPage,
  type EnrollmentSummaryPageResult,
  type WorkflowEnrollmentFilterParams,
} from '@/core/services/api/workflowEntities';
import type { WorkflowEntityState } from '@/core/services/api';
import { workflowEntityKeys } from '@/core/services/api/queryKeys';

const COLUMN_PAGE_SIZE = 20;

export type WorkflowColumnFilters = WorkflowEnrollmentFilterParams;

export function workflowColumnQueryKey(
  machineName: string,
  stateName: string,
  filters: WorkflowColumnFilters,
): QueryKey {
  return [
    ...workflowEntityKeys.column(machineName, stateName, filters.thumbnailField),
    filters.anchorEntityId ?? null,
    (filters.summaryFields ?? []).join(','),
    filters.search ?? '',
    JSON.stringify(filters.fieldFilters ?? {}),
    (filters.assigneeIds ?? []).slice().sort().join(','),
    (filters.excludeStates ?? []).slice().sort().join(','),
  ];
}

export function useWorkflowColumnEntities(
  machineName: string,
  stateName: string,
  filters: WorkflowColumnFilters,
) {
  const query = useInfiniteQuery({
    queryKey: workflowColumnQueryKey(machineName, stateName, filters),
    queryFn: async ({ pageParam }): Promise<EnrollmentSummaryPageResult> => {
      const params = buildEnrollmentQueryParams(machineName, filters);
      params.set('current_state', stateName);
      params.set('limit', String(COLUMN_PAGE_SIZE));
      params.set('offset', String(pageParam));
      return fetchEnrollmentSummaryPage(params);
    },
    initialPageParam: 0,
    // Advance by PAGES fetched, not by items held. The server's `offset`
    // counts rows the caller may read, so it stays in step with page count
    // even when a read policy drops rows — while drag-and-drop splices items
    // out of these cached pages, which would make an item-count advance skip
    // rows the user has not seen yet.
    getNextPageParam: (lastPage, allPages) =>
      lastPage.hasMore ? allPages.length * COLUMN_PAGE_SIZE : undefined,
    enabled: Boolean(machineName && stateName),
  });

  const items: WorkflowEntityState[] = query.data?.pages.flatMap((page) => page.items) ?? [];

  return {
    items,
    isLoading: query.isLoading,
    hasNextPage: Boolean(query.hasNextPage),
    isFetchingNextPage: query.isFetchingNextPage,
    fetchNextPage: query.fetchNextPage,
  };
}

type ColumnInfiniteData = { pages: EnrollmentSummaryPageResult[]; pageParams: (string | null)[] };

/** Splices `entityId` out of the source column's loaded pages and into the
 *  target column's first page, patching `current_state` in place. Returns the
 *  moved entity (for the caller to build a rollback), or null if the entity
 *  wasn't found in the source column's currently-loaded pages (it can only
 *  have been dragged from there, so this should not happen in practice). */
export function moveEntityBetweenColumnCaches(
  queryClient: QueryClient,
  machineName: string,
  filters: WorkflowColumnFilters,
  entityId: string,
  fromState: string,
  toState: string,
): WorkflowEntityState | null {
  const fromKey = workflowColumnQueryKey(machineName, fromState, filters);
  const toKey = workflowColumnQueryKey(machineName, toState, filters);

  const sourceData = queryClient.getQueryData<ColumnInfiniteData>(fromKey);
  const found = sourceData?.pages.flatMap((page) => page.items).find((item) => item.entity_id === entityId);
  if (!found) return null;

  queryClient.setQueryData<ColumnInfiniteData>(fromKey, (data) => {
    if (!data) return data;
    return {
      ...data,
      pages: data.pages.map((page) => ({
        ...page,
        items: page.items.filter((item) => item.entity_id !== entityId),
      })),
    };
  });

  const patched: WorkflowEntityState = { ...found, current_state: toState };
  queryClient.setQueryData<ColumnInfiniteData>(toKey, (data) => {
    if (!data || data.pages.length === 0) return data;
    const pages = data.pages.slice();
    pages[0] = { ...pages[0], items: [patched, ...pages[0].items] };
    return { ...data, pages };
  });
  return patched;
}
