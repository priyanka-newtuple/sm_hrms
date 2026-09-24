import type { QueryClient } from '@tanstack/react-query';
import { workflowEntityKeys } from '@/core/services/api/queryKeys';
import type { WorkflowEntityState } from '@/core/services/api';

export function invalidateWorkflowEntities(queryClient: QueryClient): void {
  void queryClient.invalidateQueries({ queryKey: workflowEntityKeys.all() });
}

interface PagedEntityCache {
  pages: Array<{ items: WorkflowEntityState[] }>;
}

/** Patches `entityId`'s `data` across every cached workflow-entity query —
 *  flat arrays (Calendar's full-drain `useWorkflowEntities`) and paginated
 *  `{pages: [...]}` shapes (kanban columns / table) alike, so an edit made
 *  from any surface shows up everywhere without a full refetch. */
export function patchWorkflowEntityData(
  queryClient: QueryClient,
  entityId: string,
  data: Record<string, unknown>,
): void {
  queryClient.getQueryCache().findAll({ queryKey: workflowEntityKeys.all() }).forEach((cacheEntry) => {
    const current = cacheEntry.state.data;
    if (Array.isArray(current)) {
      queryClient.setQueryData<WorkflowEntityState[]>(
        cacheEntry.queryKey,
        current.map((e) => (e.entity_id === entityId ? { ...e, data } : e)),
      );
      return;
    }
    const paged = current as PagedEntityCache | undefined;
    if (!paged?.pages) return;
    queryClient.setQueryData(cacheEntry.queryKey, {
      ...paged,
      pages: paged.pages.map((p) => ({
        ...p,
        items: p.items.map((e) => (e.entity_id === entityId ? { ...e, data } : e)),
      })),
    });
  });
}
