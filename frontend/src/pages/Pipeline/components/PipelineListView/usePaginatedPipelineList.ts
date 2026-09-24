import { useCallback, useEffect, useMemo, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import {
  buildEnrollmentQueryParams,
  fetchEnrollmentSummaryPage,
  type WorkflowEnrollmentFilterParams,
  type WorkflowEntityState,
} from '@/core/services/api/workflowEntities';
import { workflowEntityKeys } from '@/core/services/api/queryKeys';
import type { FieldType, FormSchema } from '@/core/types';
import type { PipelineListEntity, PipelineViewModel } from '@/shared/types/pipeline';
import { usePersistentState } from '@/core/hooks';
import { useAssigneeFilter } from '../../hooks/useAssigneeFilter';
import { useColumnPicker } from './useColumnPicker';
import type { ColumnField, ListSort, SortKey } from './types';

const TABLE_PAGE_SIZE = 20;
const NO_SCHEMAS: FormSchema[] = [];

/** Field types worth totalling. `auto_number` is deliberately absent — it is
 *  an identifier that happens to be numeric, so summing it means nothing. */
const SUMMABLE_FIELD_TYPES: ReadonlySet<FieldType> = new Set<FieldType>([
  'number',
  'integer',
  'currency',
]);

interface UsePaginatedPipelineListOptions {
  extraColumns?: ColumnField[];
  defaultVisibleFields?: string[];
  hideDueDate?: boolean;
  fixedColumns?: ColumnField[];
  /** The entity type's live form config (`GET /forms/config`), already fetched
   *  by `usePipelineBoardData`. The source of truth for which custom fields
   *  exist and what type each one is. */
  entitySchemas?: FormSchema[];
  thumbnailField?: string;
  anchorEntityId?: string | null;
  summaryFields?: string[];
  /** Page-level URL-backed search shared with the Kanban toolbar. */
  search?: string;
  onSearchChange?: (value: string) => void;
  fieldFilters?: Record<string, string | string[]>;
  /** State names to omit entirely — the Table's half of the org-wide
   *  hide-terminal toggle, so it agrees with the Kanban board rather than
   *  showing rows the board hides. */
  excludeStates?: string[];
  /** Defaults to true. Set false while the Table tab is not the active view —
   *  the hook still has to be called (rules of hooks), but shouldn't spend a
   *  request fetching a page nobody is looking at. */
  enabled?: boolean;
}

const FIXED_SORT_PARAM: Record<string, string> = {
  entity: 'display_name',
  identifier: 'identifier',
  state: 'state',
  created: 'created',
  due_date: 'due_date',
};

const EXPORT_PAGE_SIZE = 200;

/** Whether an already-sorted requested set still matches what's needed. */
function sameFieldIds(requested: string[], needed: string[]): boolean {
  const sorted = [...requested].sort();
  return sorted.length === needed.length && sorted.every((id, i) => id === needed[i]);
}

/** Map a raw `WorkflowEntityState` to the `PipelineListEntity` shape the table
 *  and export consume, filling missing timestamps from the next best available.
 *
 *  Deliberately not the `toListEntity` exported from `usePipelineBoardData`:
 *  that one falls back to `new Date()` for a missing date, this one to the
 *  epoch, so sharing it would move dateless rows from the bottom of a date
 *  sort to the top. */
function toListEntity(entity: WorkflowEntityState): PipelineListEntity {
  return {
    entity_id: entity.entity_id,
    state_id: entity.state_id,
    workflow_id: entity.workflow_id,
    current_state: entity.current_state,
    created_at: entity.created_at ?? entity.state_entered_at ?? new Date(0).toISOString(),
    updated_at: entity.updated_at ?? entity.created_at ?? new Date(0).toISOString(),
    data: entity.data,
    due_date: entity.due_date,
    assignee_id: entity.assignee_id,
    assignee_name: entity.assignee_name,
    transition_options: entity.transition_options,
  };
}

export function usePaginatedPipelineList(
  model: PipelineViewModel,
  machineName: string,
  options?: UsePaginatedPipelineListOptions,
) {
  const [search, setSearch] = useState('');
  const [stateFilter, setStateFilter] = useState('');
  const [identifierFilter, setIdentifierFilter] = useState('');
  const [page, setPage] = useState(0);
  const [sort, setSort] = usePersistentState<ListSort>(
    `pipeline-list:sort:${model.machineName}`,
    { key: '', dir: 'asc' },
  );

  const assigneeFilter = useAssigneeFilter(model.machineName);
  const effectiveSearch = options?.onSearchChange ? options.search ?? '' : search;

  // The server only returns `data.*` keys actually asked for (`fields=...`,
  // narrowed for latency vs. a single-entity fetch) — `options?.summaryFields`
  // is a static base (title/subtitle/thumbnail from the skin config). Custom
  // columns the user toggles on via the Columns picker were never added to
  // that request, so their cells stayed blank regardless of any filter.
  // Bridged in below from `visibleColumns` (real currently-visible custom
  // fields) once computed — starts empty so the very first fetch matches
  // today's behavior; updates (and refetches) once the actual toggled set is
  // known, converging in at most one extra round-trip on mount/toggle.
  const [requestedCustomFieldIds, setRequestedCustomFieldIds] = useState<string[]>([]);
  // Totals ride the same already-existing refetch: toggling a custom column
  // re-requests its `data.*` key anyway, so this adds no extra round trip.
  const [requestedSumFieldIds, setRequestedSumFieldIds] = useState<string[]>([]);

  const filters: WorkflowEnrollmentFilterParams = useMemo(
    () => ({
      thumbnailField: options?.thumbnailField,
      anchorEntityId: options?.anchorEntityId,
      summaryFields: Array.from(
        new Set([...(options?.summaryFields ?? []), ...requestedCustomFieldIds]),
      ),
      search: effectiveSearch,
      fieldFilters: options?.fieldFilters,
      identifier: identifierFilter || undefined,
      assigneeIds: assigneeFilter.selectedIds.length ? assigneeFilter.selectedIds : undefined,
      excludeStates: options?.excludeStates?.length ? options.excludeStates : undefined,
      sumFields: requestedSumFieldIds,
    }),
    [options?.thumbnailField, options?.anchorEntityId, options?.summaryFields, requestedCustomFieldIds, requestedSumFieldIds, options?.fieldFilters, effectiveSearch, identifierFilter, assigneeFilter.selectedIds, options?.excludeStates],
  );

  const sortByParam = sort.key ? FIXED_SORT_PARAM[sort.key] : undefined;

  // Everything that narrows the result set except the identifier selection and
  // the page — the identifier dropdown's own options must not shrink to the
  // value you just picked, and they don't vary by page.
  const facetKey = useMemo(
    () => [
      ...workflowEntityKeys.table(machineName, options?.thumbnailField),
      filters.anchorEntityId ?? null,
      (filters.summaryFields ?? []).join(','),
      filters.search ?? '',
      JSON.stringify(filters.fieldFilters ?? {}),
      (filters.assigneeIds ?? []).slice().sort().join(','),
      (filters.excludeStates ?? []).slice().sort().join(','),
      stateFilter,
    ],
    [machineName, options?.thumbnailField, filters, stateFilter],
  );

  // `sumFields` belongs to the page query alone — the identifier-options query
  // shares `facetKey` and would otherwise pay for an aggregate it never reads.
  const queryKey = useMemo(
    () => [
      ...facetKey,
      'page',
      filters.identifier ?? '',
      (filters.sumFields ?? []).join(','),
      sortByParam ?? '',
      sort.dir,
      page,
    ],
    [facetKey, filters.identifier, filters.sumFields, sortByParam, sort.dir, page],
  );

  const { data, isLoading } = useQuery({
    queryKey,
    queryFn: async () => {
      const params = buildEnrollmentQueryParams(machineName, filters);
      if (stateFilter) params.set('current_state', stateFilter);
      if (sortByParam) {
        params.set('sort_by', sortByParam);
        params.set('sort_dir', sort.dir);
      }
      params.set('offset', String(page * TABLE_PAGE_SIZE));
      params.set('limit', String(TABLE_PAGE_SIZE));
      params.set('include', 'total_count');
      return fetchEnrollmentSummaryPage(params);
    },
    enabled: Boolean(machineName) && (options?.enabled ?? true),
    // Each page is its own cache entry, so without this `data` goes undefined
    // for the duration of every page change — which both flashes an empty
    // table and (worse) made `totalCount` read 0 mid-flight, tripping the
    // out-of-range clamp below into bouncing the user straight back to page 1.
    // Holding the previous page's data keeps the row count meaningful while
    // the next page loads.
    placeholderData: keepPreviousData,
  });

  // Its own query, keyed without `page` or `identifier` — the dropdown's
  // contents are a property of the filter set, not of where you are in it, so
  // paging must neither refetch them nor let them flicker.
  const { data: identifierOptions } = useQuery({
    queryKey: [...facetKey, 'identifier-options'],
    queryFn: async () => {
      const params = buildEnrollmentQueryParams(machineName, {
        ...filters,
        identifier: undefined,
        sumFields: undefined,
      });
      if (stateFilter) params.set('current_state', stateFilter);
      params.set('limit', '1');
      params.set('include', 'identifier_options');
      return (await fetchEnrollmentSummaryPage(params)).identifierOptions ?? [];
    },
    enabled: Boolean(machineName) && (options?.enabled ?? true),
  });

  // Filters that change from OUTSIDE this hook — the URL-backed assignee
  // selection (written by the page-level avatar filter) and the org-wide
  // hide-terminal toggle — never pass through the setters below, so they need
  // their own reset. Without it, narrowing the result set while on page 5
  // keeps requesting offset=80: the table renders empty, and because the pager
  // only shows when totalCount > pageSize it also disappears, leaving no way
  // back to page 1.
  const externalFilterSignature = [
    (filters.assigneeIds ?? []).slice().sort().join(','),
    (filters.excludeStates ?? []).slice().sort().join(','),
    filters.search ?? '',
    JSON.stringify(filters.fieldFilters ?? {}),
  ].join('|');
  useEffect(() => {
    setPage(0);
  }, [externalFilterSignature]);

  // Safety net for any other way the page can end up past the end (data
  // shrinking underneath a held page, a reset racing a refetch): clamp back
  // into range instead of showing an empty table. Only ever act on a real
  // count — clamping against a not-yet-loaded `undefined` would treat every
  // in-flight page as "out of range" and undo the navigation.
  const totalCount = data?.totalCount ?? 0;
  const fieldTotals = data?.fieldTotals ?? null;
  const pageCount = Math.max(1, Math.ceil(totalCount / TABLE_PAGE_SIZE));
  const hasCount = data !== undefined;
  useEffect(() => {
    if (hasCount && page > pageCount - 1) setPage(pageCount - 1);
  }, [hasCount, page, pageCount]);

  const rows = data?.items.map(toListEntity) ?? [];

  const { allFields, effectiveFieldIds, visibleColumns, toggleField } = useColumnPicker(
    model,
    options?.entitySchemas ?? NO_SCHEMAS,
    rows,
    {
      extraColumns: options?.extraColumns,
      fixedColumns: options?.fixedColumns,
      defaultVisibleFields: options?.defaultVisibleFields,
    },
  );

  // Sync the request to whatever's actually visible: `visibleColumns` is
  // already "custom (non-fixed) fields currently toggled on"; drop the
  // synthetic accessor-based ones (e.g. the aggregate view's Workflow/Owner
  // columns), which don't read from `entity.data` and so have nothing to fetch.
  const neededCustomFieldIds = useMemo(
    () =>
      visibleColumns
        .filter((c) => !c.accessor)
        .map((c) => c.field)
        .sort(),
    [visibleColumns],
  );
  // Only the visible columns whose live form-config type is worth totalling —
  // a column with no configured type (a bare `data` key) is never summed.
  const neededSumFieldIds = useMemo(
    () =>
      visibleColumns
        .filter((c) => !c.accessor && c.type && SUMMABLE_FIELD_TYPES.has(c.type))
        .map((c) => c.field)
        .sort(),
    [visibleColumns],
  );
  // Adjust state during render (not in an effect) when the toggled selection
  // has actually changed — the sanctioned React pattern for "derive state from
  // a value computed this render": React re-runs the component immediately
  // with the new value before committing, so `filters`/`queryKey` below always
  // see the up-to-date set in the same pass, no extra effect round-trip.
  if (!sameFieldIds(requestedCustomFieldIds, neededCustomFieldIds)) {
    setRequestedCustomFieldIds(neededCustomFieldIds);
  }
  if (!sameFieldIds(requestedSumFieldIds, neededSumFieldIds)) {
    setRequestedSumFieldIds(neededSumFieldIds);
  }

  const toggleSort = (key: SortKey) =>
    setSort((prev) =>
      prev.key === key
        ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' }
        : { key, dir: 'asc' },
    );

   /** Every row for the current filters, carrying the requested `data.*` keys —
   *  the table holds one page of visible columns, and nothing in Kanban. */
  const fetchAllRows = useCallback(
    async (dataFieldIds: string[]): Promise<PipelineListEntity[]> => {
      if (!machineName) return [];
      const collected: PipelineListEntity[] = [];
      for (let offset = 0; ; offset += EXPORT_PAGE_SIZE) {
        const params = buildEnrollmentQueryParams(machineName, {
          ...filters,
          sumFields: undefined,
          summaryFields: Array.from(
            new Set([...(filters.summaryFields ?? []), ...dataFieldIds]),
          ),
        });
        if (stateFilter) params.set('current_state', stateFilter);
        if (sortByParam) {
          params.set('sort_by', sortByParam);
          params.set('sort_dir', sort.dir);
        }
        params.set('offset', String(offset));
        params.set('limit', String(EXPORT_PAGE_SIZE));
        const page = await fetchEnrollmentSummaryPage(params);
        collected.push(...page.items.map(toListEntity));
        // Short page (or none) means that was the last one.
        if (page.items.length < EXPORT_PAGE_SIZE) break;
      }
      return collected;
    },
    [machineName, filters, stateFilter, sortByParam, sort.dir],
  );

 return {
    search: effectiveSearch,
    setSearch: (value: string) => {
      if (options?.onSearchChange) options.onSearchChange(value);
      else setSearch(value);
      setPage(0);
    },
    stateFilter,
    setStateFilter: (value: string) => { setStateFilter(value); setPage(0); },
    identifierFilter,
    setIdentifierFilter: (value: string) => { setIdentifierFilter(value); setPage(0); },
    identifierOptions: identifierOptions ?? [],
    allFields,
    effectiveFieldIds,
    visibleColumns,
    sort,
    toggleSort: (key: SortKey) => { toggleSort(key); setPage(0); },
    toggleField,
    rows,
    fetchAllRows,
    totalCount,
    fieldTotals,
    page,
    setPage,
    pageSize: TABLE_PAGE_SIZE,
    isLoading,
  };
}
