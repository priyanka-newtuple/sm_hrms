import { useCallback, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { useSkin } from '@/skins';
import { useFeatureFlags } from '@/core/hooks/useFeatureFlags';
import { listOrgUsers } from '@/core/services/api/workflowEntities';

/** Sentinel assignee-filter value meaning "no assignee". Matches the
 *  backend's `UNASSIGNED_FILTER_SENTINEL` and `ENROLLMENT_UNASSIGNED_SENTINEL`
 *  in workflowEntities.ts. */
export const UNASSIGNED_FILTER = '__unassigned__';

interface AssigneeLike {
  assignee_id?: string;
}

interface AssigneeOption {
  id: string;
  name: string;
}

const NOOP = () => {};
const DISABLED_RESULT = {
  options: [] as AssigneeOption[],
  hasUnassigned: false,
  selectedIds: [] as string[],
  toggle: NOOP as (id: string) => void,
  clear: NOOP,
  matches: () => true,
};

/**
 * Shared, URL-backed, multi-select assignee filter — one instance per
 * workflow (keyed by machine name) so Board/Table/Calendar read/write the
 * same selection. Options list is every org user (via `listOrgUsers`), not
 * "assignees seen in loaded rows" — the board/table no longer load
 * everything up front, so a loaded-rows-derived list would be an
 * arbitrarily incomplete dropdown depending on scroll/page position.
 * "Unassigned" is always offered (not conditional on any currently-loaded
 * row actually being unassigned) for the same reason.
 *
 * Off by default; an org admin opts in per-org via Settings → Display
 * (`featureFlags.hideAssigneeFilter: false`). A skin can also hard-disable it
 * via `skin.board.showAssigneeFilter: false`, which wins regardless of the
 * org's setting — for entity models where "assignee" isn't a meaningful
 * concept at all.
 */
export function useAssigneeFilter(machineName: string) {
  const { skin } = useSkin();
  const { hideAssigneeFilter } = useFeatureFlags();
  const enabled = skin.board.showAssigneeFilter !== false && !hideAssigneeFilter;
  const paramKey = `filter_assignee_${machineName}`;
  const [searchParams, setSearchParams] = useSearchParams();
  // useSearchParams() returns a new URLSearchParams instance every render even
  // when nothing changed — reading the raw string first and memoizing on that
  // (a primitive, stable by value) keeps `selectedIds`'s array identity stable
  // too, instead of recomputing on every render and cascading instability into
  // every callback/memo derived from it (which previously caused an infinite
  // re-render loop wherever a caller depended on this hook's return value).
  const rawValue = searchParams.get(paramKey) ?? '';
  const selectedIds = useMemo(() => (rawValue ? rawValue.split(',').filter(Boolean) : []), [rawValue]);

  const setSelectedIds = useCallback(
    (ids: string[]) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (ids.length > 0) next.set(paramKey, ids.join(','));
          else next.delete(paramKey);
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams, paramKey],
  );

  const toggle = useCallback(
    (id: string) => {
      setSelectedIds(
        selectedIds.includes(id) ? selectedIds.filter((existing) => existing !== id) : [...selectedIds, id],
      );
    },
    [selectedIds, setSelectedIds],
  );

  const clear = useCallback(() => setSelectedIds([]), [setSelectedIds]);

  const { data: orgUsers } = useQuery({
    queryKey: ['orgUsers', 'assigneeFilterOptions'],
    queryFn: listOrgUsers,
    enabled,
    staleTime: 5 * 60 * 1000,
  });
  const options = useMemo(
    () => [...(orgUsers ?? [])].sort((a, b) => a.name.localeCompare(b.name)),
    [orgUsers],
  );

  const matches = useCallback(
    (entity: AssigneeLike) =>
      selectedIds.length === 0 ||
      selectedIds.some((id) => (id === UNASSIGNED_FILTER ? !entity.assignee_id : entity.assignee_id === id)),
    [selectedIds],
  );

  return useMemo(
    () => (enabled ? { options, hasUnassigned: true, selectedIds, toggle, clear, matches } : DISABLED_RESULT),
    [enabled, options, selectedIds, toggle, clear, matches],
  );
}
