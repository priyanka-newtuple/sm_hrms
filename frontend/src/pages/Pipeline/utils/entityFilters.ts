import type { UserPublic } from '@/core/auth';
import type { WorkflowEntityState } from '@/core/services/api';

interface PipelineEntityFilterOptions {
  applyBoardFilters: (entities: WorkflowEntityState[]) => WorkflowEntityState[];
  filterVisibleEntity?: (entity: WorkflowEntityState, user: UserPublic | null) => boolean;
  user: UserPublic | null;
}

/** Applies skin-configured board-level visibility rules — `filterBar` and
 *  `filterVisibleEntities` — over whatever's currently loaded for a view.
 *  Search/assignee/hide-terminal-states are server-side query params now
 *  (see useWorkflowColumnEntities / usePaginatedPipelineList), not filtered
 *  here. No current caller invokes this — confirmed zero skins in this repo
 *  configure `filterBar`/`filterVisibleEntities` — kept as the seam a
 *  per-view (StateColumn / PipelineListView) integration would call into if
 *  a future skin needs it. */
export function filterPipelineEntities(
  entities: WorkflowEntityState[],
  options: PipelineEntityFilterOptions,
): WorkflowEntityState[] {
  let filtered = options.applyBoardFilters(entities);
  if (options.filterVisibleEntity) {
    filtered = filtered.filter((entity) => options.filterVisibleEntity?.(entity, options.user));
  }
  return filtered;
}
