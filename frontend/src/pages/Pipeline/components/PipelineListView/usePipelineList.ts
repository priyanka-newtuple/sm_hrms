import { useEffect, useMemo, useState } from 'react';
import type { FormSchema } from '@/core/types';
import type { PipelineListEntity, PipelineViewModel } from '@/shared/types/pipeline';
import { getEntityPrimaryValue } from '@/shared/utils/entityDisplay';
import { IDENTIFIER_FIELD_KEY } from '@/shared/utils/entityForm';
import { usePersistentState } from '@/core/hooks';
import { useAssigneeFilter } from '../../hooks/useAssigneeFilter';
import { useColumnPicker } from './useColumnPicker';
import type { ColumnField, ListSort, SortKey } from './types';
import { compareValues } from './utils';

/**
 * Controller hook for the pipeline list view. Owns all interaction state
 * (search, state filter, column visibility, sort — the latter two persisted
 * per machine) and derives the filtered + sorted rows and column set.
 *
 * @param model - pipeline view-model providing schema fields, states, etc.
 * @param entities - raw entities to display.
 */
interface UsePipelineListOptions {
  /** Non-data columns (e.g. Workflow, Owner) backed by an `accessor`. Shown
   *  ahead of schema/data columns and selectable in the column menu. */
  extraColumns?: ColumnField[];
  /** Field ids visible by default; falls back to the first column. */
  defaultVisibleFields?: string[];
  /** Exclude the first-class Due date value from search and sorting. */
  hideDueDate?: boolean;
  /** The caller's fixed/structural columns (Identifier, Due date, Status,
   *  Owner, Created) that are candidates for the column picker alongside
   *  schema/data fields — but, unlike those, default to visible so nobody
   *  loses a column they never asked to hide. Rendered specially by the
   *  caller (badges, avatars, etc.), not via the generic `visibleColumns`
   *  path — this hook only tracks their visibility, not their content. */
  fixedColumns?: ColumnField[];
  /** The entity type's live form config, used to discover custom-field column
   *  candidates. Omitted by the cross-workflow aggregate view, which spans
   *  heterogeneous entity types and so has no single form config to read —
   *  there, columns are discovered from the rows' own `data` keys. */
  entitySchemas?: FormSchema[];
  /** See `useColumnPicker`. Calendar borrows this hook for search/filters only
   *  and renders no columns, so it must not repair the shared selection. */
  ownsColumnSelection?: boolean;
}

const PAGE_SIZE = 20;
const NO_SCHEMAS: FormSchema[] = [];

export function usePipelineList(
  model: PipelineViewModel,
  entities: PipelineListEntity[],
  options?: UsePipelineListOptions,
) {
  const [search, setSearch] = useState('');
  const [stateFilter, setStateFilter] = useState('');
  const [identifierFilter, setIdentifierFilter] = useState('');

  // Shared, URL-backed, per-workflow assignee filter — the same instance the
  // Board tab's toolbar renders, so Board/Table/Calendar all read one selection.
  const assigneeFilter = useAssigneeFilter(model.machineName);

  // Distinct identifier values across entities, for the identifier dropdown.
  const identifierOptions = useMemo(() => {
    const values = new Set<string>();
    for (const e of entities) {
      const v = String(e.data[IDENTIFIER_FIELD_KEY] ?? '').trim();
      if (v) values.add(v);
    }
    return Array.from(values).sort();
  }, [entities]);

  const {
    allFields,
    effectiveFieldIds,
    visibleColumns,
    accessorByField,
    toggleField,
  } = useColumnPicker(model, options?.entitySchemas ?? NO_SCHEMAS, entities, {
    extraColumns: options?.extraColumns,
    fixedColumns: options?.fixedColumns,
    defaultVisibleFields: options?.defaultVisibleFields,
    ownsColumnSelection: options?.ownsColumnSelection,
  });

  const [sort, setSort] = usePersistentState<ListSort>(
    `pipeline-list:sort:${model.machineName}`,
    { key: '', dir: 'asc' },
  );

  const sortValue = useMemo(() => {
    return (e: PipelineListEntity): unknown => {
      switch (sort.key) {
        case '':
          return null;
        case 'entity':
          return getEntityPrimaryValue(e.data, e.entity_id);
        case 'identifier':
          return String(e.data[IDENTIFIER_FIELD_KEY] ?? '');
        case 'state':
          return model.stateById.get(e.current_state)?.label ?? e.current_state;
        case 'created':
          return new Date(e.created_at).getTime();
        case 'due_date':
          return e.due_date ?? '';
        default: {
          const accessor = accessorByField.get(sort.key);
          return accessor ? accessor(e) : e.data[sort.key];
        }
      }
    };
  }, [sort.key, model, accessorByField]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    const rows = entities.filter((e) => {
      const matchesState = !stateFilter || e.current_state === stateFilter;
      const matchesIdentifier =
        !identifierFilter ||
        String(e.data[IDENTIFIER_FIELD_KEY] ?? '').trim() === identifierFilter;
      const matchesAssignee = assigneeFilter.matches(e);
      const matchesSearch =
        !q ||
        e.entity_id.toLowerCase().includes(q) ||
        (!options?.hideDueDate && Boolean(e.due_date?.toLowerCase().includes(q))) ||
        Object.values(e.data).some((v) => String(v ?? '').toLowerCase().includes(q)) ||
        Array.from(accessorByField.values()).some((acc) =>
          String(acc(e) ?? '').toLowerCase().includes(q),
        );
      return matchesState && matchesIdentifier && matchesAssignee && matchesSearch;
    });

    if (!sort.key || (options?.hideDueDate && sort.key === 'due_date')) return rows;
    return [...rows].sort((a, b) => {
      const cmp = compareValues(sortValue(a), sortValue(b));
      return sort.dir === 'asc' ? cmp : -cmp;
    });
  }, [entities, search, stateFilter, identifierFilter, assigneeFilter, sort, sortValue, accessorByField, options?.hideDueDate]);

  const [page, setPage] = useState(0);
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  useEffect(() => {
    setPage((current) => Math.min(current, pageCount - 1));
  }, [pageCount]);
  useEffect(() => {
    setPage(0);
  }, [search, stateFilter, identifierFilter, sort]);
  const rows = useMemo(
    () => filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE),
    [filtered, page],
  );

  const toggleSort = (key: SortKey) =>
    setSort((prev) =>
      prev.key === key
        ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' }
        : { key, dir: 'asc' },
    );

  return {
    search,
    setSearch,
    stateFilter,
    setStateFilter,
    identifierFilter,
    setIdentifierFilter,
    identifierOptions,
    allFields,
    effectiveFieldIds,
    visibleColumns,
    sort,
    toggleSort,
    toggleField,
    /** Full filtered+sorted set, unpaginated — Calendar renders every match
     *  in the visible month, not one page of it. */
    filtered,
    /** This page only (`PAGE_SIZE` at a time) — matches
     *  `PipelineListController`'s shape so `PipelineListView` can drive
     *  either this hook or `usePaginatedPipelineList` the same way. */
    rows,
    totalCount: filtered.length,
    /** No server aggregate behind this controller — the Calendar and the
     *  cross-workflow aggregate view don't offer a totals row. */
    fieldTotals: null,
    page,
    setPage,
    pageSize: PAGE_SIZE,
  };
}
