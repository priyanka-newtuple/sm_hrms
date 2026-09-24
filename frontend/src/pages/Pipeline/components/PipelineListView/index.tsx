import { useEffect, useMemo, useRef, type ReactNode } from 'react';
import Card from '@/core/components/Card';
import { cn } from '@/lib/utils';
import type { PipelineListEntity, PipelineViewModel } from '@/shared/types/pipeline';
import { useColumnLabels, useColumnOrder, applyColumnOrder } from '@/shared/hooks';
import { useFeatureFlags } from '@/core/hooks/useFeatureFlags';
import { picklistLabel } from '@/core/utils';
import { getEntityPrimaryValue, formatCurrencyValue } from '@/shared/utils/entityDisplay';
import { IDENTIFIER_FIELD_KEY, getIdentifierLabel } from '@/shared/utils/entityForm';
import {
  isFieldTotalError,
  type FieldTotalError,
  type FieldTotalValue,
} from '@/core/services/api/workflowEntities';
import { resolveStateLabel } from '@/shared/utils/labels';
import { getInitials, getAvatarColorClass } from '@/core/utils';
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from '@/components/ui/pagination';
import { usePipelineList } from './usePipelineList';
import PipelineListToolbar from './PipelineListToolbar';
import ColumnVisibilityMenu from '@/shared/components/ColumnVisibilityMenu';
import PipelineListTable from './PipelineListTable';
import { formatDate } from './utils';
import { FIELD_GROUP, type ColumnDescriptor, type ColumnField, type PipelineListController } from './types';
import { getDueDatePresentation } from '../../utils/dueDate';
import BulkActionBar from '../PipelineKanbanBoard/BulkActionBar';
import { useBulkEntityActions } from '../../hooks/useBulkEntityActions';

type ListFieldMeta = {
  type?: string;
  enum_values?: string[];
  enum_labels?: string[];
};

function renderCellValue(value: unknown): ReactNode {
  if (value === null || value === undefined || value === '') {
    return <span className="text-muted-foreground/45">—</span>;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-muted-foreground/45">—</span>;
    const rendered = value
      .map((item) => {
        if (item === null || item === undefined) return '';
        if (typeof item === 'object') {
          const record = item as Record<string, unknown>;
          const label = record.label ?? record.name ?? record.description ?? record.value;
          return label == null ? '' : String(label);
        }
        return String(item);
      })
      .filter(Boolean);
    if (rendered.length > 0) return rendered.join(', ');
    return `${value.length} ${value.length === 1 ? 'row' : 'rows'}`;
  }
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>;
    if (record.__type === 'currency' || ('amount' in record && 'currency_code' in record)) {
      const code = typeof record.currency_code === 'string' ? record.currency_code : '';
      return formatCurrencyValue(record.amount, code);
    }
    return String(
      record.label ??
        record.name ??
        record.description ??
        record.value ??
        JSON.stringify(record),
    );
  }
  return String(value);
}

function resolvePicklistDisplayValue(field: ListFieldMeta | undefined, value: unknown): string | null {
  if (!field?.enum_values?.length) return null;
  if (Array.isArray(value)) {
    if (value.some((item) => item !== null && typeof item === 'object')) return null;
    const labels = value
      .map((item) => picklistLabel(field, item) ?? (item == null ? '' : String(item)))
      .filter(Boolean);
    return labels.length > 0 ? labels.join(', ') : null;
  }
  return picklistLabel(field, value);
}

function DueDateCell({ value }: { value?: string }) {
  const dueDate = getDueDatePresentation(value);
  if (!dueDate) return <span className="text-muted-foreground/45">—</span>;

  return (
    <div className="flex min-w-28 flex-col items-start">
      <span className="whitespace-nowrap text-[13px] font-normal text-foreground">
        {dueDate.label}
      </span>
      {dueDate.status === 'overdue' && (
        <span className="mt-1 inline-flex rounded-full bg-destructive px-3 py-1 text-xs font-normal leading-none text-destructive-foreground">
          Overdue
        </span>
      )}
      {dueDate.status === 'today' && (
        <span className="mt-1 inline-flex rounded-full bg-[#302b38] px-3 py-1 text-xs font-normal leading-none text-white">
          Due today
        </span>
      )}
    </div>
  );
}

interface PipelineListViewProps {
  model: PipelineViewModel;
  /** Full drained-client-side dataset. Ignored when `controller` is passed —
   *  required only for the uncontrolled (Calendar-adjacent aggregate view)
   *  path, where this component builds its own `usePipelineList` instance. */
  entities?: PipelineListEntity[];
  /** Server-paginated controller (from `usePaginatedPipelineList`) — when
   *  present, this component renders purely from it instead of building its
   *  own client-side `usePipelineList` controller from `entities`. Always
   *  calls `usePipelineList` internally regardless (rules of hooks), but its
   *  result is simply unused in that case. */
  controller?: PipelineListController;
  onEntityClick?: (entityId: string, workflowId?: string) => void;
  /** Non-data columns (Workflow, Owner) for the aggregated view. */
  extraColumns?: ColumnField[];
  /** Field ids visible by default. */
  defaultVisibleFields?: string[];
  /** Entity-type filter (aggregated cross-workflow view). */
  entityTypes?: string[];
  entityTypeFilter?: string;
  onEntityTypeFilterChange?: (value: string) => void;
  /** Override the state-filter dropdown options (aggregated view). */
  stateOptions?: { id: string; label: string }[];
  /** When false, the Created column is hidden. */
  showCreated?: boolean;
  /** When true, shows an Assignee column + an "Assigned to" filter. */
  showAssignee?: boolean;
  /** When true, a per-row actions (…) menu with available transitions is shown. */
  enableRowTransitions?: boolean;
  onTransitionExecuted?: () => void;
  /** Enables row selection with shared bulk transition/delete actions. */
  enableBulkActions?: boolean;
  canDelete?: boolean;
  onBulkMutationCommitted?: () => void;
  /** Parent-owned form-filter signature used to discard hidden selections. */
  bulkSelectionScopeKey?: string;
  /** Hide the local search when a parent toolbar owns the shared search input. */
  showSearch?: boolean;
  /** Optional row-aware metadata used to map stored picklist values to labels. */
  resolveFieldMeta?: (entity: PipelineListEntity, fieldId: string) => ListFieldMeta | undefined;
  /** Called whenever the filtered+sorted rows change, so a parent can mirror
   *  what the user sees (e.g. for export). */
  onFilteredEntitiesChange?: (rows: PipelineListEntity[]) => void;
}

const NO_ENTITIES: PipelineListEntity[] = [];
const NOOP = () => {};

/** Below this many matching records a total says nothing the rows don't. */
const MIN_ROWS_FOR_SUMMARY = 2;

/** One summed column's cell: the total, or why there isn't one.
 *  The currency comes from the aggregate itself — it covers the whole filtered
 *  set, so it cannot be read off whichever rows this page happens to show. */
function SummaryTotalCell({ total }: { total: FieldTotalValue | FieldTotalError }) {
  if (isFieldTotalError(total)) {
    return (
      <span
        className="cursor-help font-normal text-muted-foreground/70"
        title={total.message}
      >
        Mixed {total.currency_codes.join(' / ')}
      </span>
    );
  }
  return (
    <span>
      {total.currency_code
        ? formatCurrencyValue(total.total, total.currency_code)
        : total.total.toLocaleString()}
    </span>
  );
}

/** Pages shown either side of the current one before collapsing to an ellipsis. */
const PAGE_WINDOW = 1;
/** Below this many pages, show every page number — no ellipsis needed. */
const ALL_PAGES_THRESHOLD = 7;

/** Page indices (0-based) to render, with 'ellipsis' marking collapsed gaps.
 *  Always keeps the first and last page reachable in one click. */
function buildPageItems(current: number, pageCount: number): Array<number | 'ellipsis'> {
  if (pageCount <= ALL_PAGES_THRESHOLD) {
    return Array.from({ length: pageCount }, (_, index) => index);
  }
  const last = pageCount - 1;
  const start = Math.max(1, current - PAGE_WINDOW);
  const end = Math.min(last - 1, current + PAGE_WINDOW);
  const items: Array<number | 'ellipsis'> = [0];
  if (start > 1) items.push('ellipsis');
  for (let page = start; page <= end; page += 1) items.push(page);
  if (end < last - 1) items.push('ellipsis');
  items.push(last);
  return items;
}

/** List view of pipeline entities: drag-reorderable, sortable columns. */
export default function PipelineListView({
  model,
  entities,
  controller,
  onEntityClick,
  extraColumns,
  defaultVisibleFields,
  entityTypes,
  entityTypeFilter,
  onEntityTypeFilterChange,
  stateOptions,
  showCreated = true,
  showAssignee = false,
  enableRowTransitions = false,
  onTransitionExecuted,
  enableBulkActions = false,
  canDelete = false,
  onBulkMutationCommitted,
  bulkSelectionScopeKey = '',
  showSearch = true,
  resolveFieldMeta,
  onFilteredEntitiesChange,
}: PipelineListViewProps) {
  const labels = useColumnLabels();
  const { order, setOrder } = useColumnOrder();
  const { hideDueDate } = useFeatureFlags();

  // The structural columns this view can show — candidates for the same
  // column picker as custom fields, but (via usePipelineList's fixedColumns
  // handling) defaulting to visible so nobody loses one they never chose to
  // hide. Only offered when actually possible for this view (e.g. no "Owner"
  // option when the workflow has no assignee concept) — the picker toggles
  // whether a possible column is shown, it doesn't resurrect impossible ones.
  const fixedColumns = useMemo<ColumnField[]>(() => {
    const cols: ColumnField[] = [
      { field: 'entity', label: labels.entity, group: FIELD_GROUP.STANDARD },
      { field: 'identifier', label: getIdentifierLabel(model.entityType), group: FIELD_GROUP.STANDARD },
    ];
    if (!hideDueDate) cols.push({ field: 'due_date', label: 'Due date', group: FIELD_GROUP.STANDARD });
    cols.push({ field: 'state', label: labels.state, group: FIELD_GROUP.STANDARD });
    if (showAssignee) cols.push({ field: 'assignee', label: 'Owner', group: FIELD_GROUP.STANDARD });
    if (showCreated) cols.push({ field: 'created', label: labels.created, group: FIELD_GROUP.STANDARD });
    return cols;
  }, [model.entityType, hideDueDate, labels.entity, labels.state, labels.created, showAssignee, showCreated]);

  // Always called (rules of hooks) — its result is simply unused when
  // `controller` (server-paginated) is supplied instead.
  const localController = usePipelineList(model, entities ?? NO_ENTITIES, {
    extraColumns,
    fixedColumns,
    defaultVisibleFields,
    hideDueDate,
  });
  const listState = controller ?? localController;
  const {
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
    rows,
    totalCount,
    fieldTotals,
    page,
    setPage,
    pageSize,
  } = listState;
  const bulk = useBulkEntityActions({
    onCommitted: onBulkMutationCommitted ?? NOOP,
    scopeKey: [bulkSelectionScopeKey, search, stateFilter, identifierFilter].join('|'),
  });

  // Reset to page 1 when the caller's own entityTypeFilter changes — that
  // filter lives outside this hook (aggregate cross-workflow view only).
  useEffect(() => {
    setPage(0);
  }, [entityTypeFilter, setPage]);

  // `rows` is a fresh array on every render, so only notify the parent when
  // the actual row set changes. The signature includes `updated_at` (not just
  // id + order) so that a data edit which leaves the visible rows unchanged
  // still re-emits — otherwise the parent, which resets to the full list on
  // every refetch, keeps the full set and the export downloads filtered rows.
  // Without this guard the parent's state update would loop on every render.
  // Note: for the server-paginated controller this is "this page only", not
  // every filtered row — exporting/iterating beyond the current page isn't
  // supported yet (see the Plan A spec's scope notes).
  const lastFilteredSig = useRef<string | null>(null);
  useEffect(() => {
    const sig = rows.map((e) => `${e.entity_id}:${e.updated_at}`).join('|');
    if (sig !== lastFilteredSig.current) {
      lastFilteredSig.current = sig;
      onFilteredEntitiesChange?.(rows);
    }
  }, [rows, onFilteredEntitiesChange]);

  // Build the full ordered column set: whichever of Name/Identifier/Due
  // date/Status/Owner/Created the user has toggled on, plus the toggled
  // data/extra columns. The saved org-wide order is then applied; unknown/new
  // columns fall back to this default order.
  const columns = useMemo<ColumnDescriptor[]>(() => {
    const isFixedColumnVisible = (id: string) => effectiveFieldIds.includes(id);
    const cols: ColumnDescriptor[] = [];
    if (isFixedColumnVisible('entity')) {
      cols.push({
        id: 'entity',
        label: labels.entity,
        render: (e) => (
          <div className="min-w-0">
            <div className="truncate text-[13px] font-medium text-foreground">
              {getEntityPrimaryValue(e.data, e.entity_id)}
            </div>
          </div>
        ),
      });
    }
    if (isFixedColumnVisible('identifier')) {
      cols.push({
        id: 'identifier',
        label: getIdentifierLabel(model.entityType),
        render: (e) => {
          const v = e.data[IDENTIFIER_FIELD_KEY];
          return renderCellValue(v);
        },
      });
    }
    cols.push(
      ...visibleColumns.map<ColumnDescriptor>((col) => ({
        id: col.field,
        label: col.label,
        // Server-side sort (usePaginatedPipelineList) only supports the
        // fixed columns below (entity/identifier/state/due_date/created) —
        // custom schema-field sort is Plan B, so disable the header click
        // for custom columns only when server-paginated. The uncontrolled
        // client-side path (usePipelineList — Calendar / aggregate widget)
        // keeps sorting these exactly as it always has.
        sortKey: controller ? null : undefined,
        render: (e) => {
          const v = col.accessor ? col.accessor(e) : e.data[col.field];
          const label = resolvePicklistDisplayValue(resolveFieldMeta?.(e, col.field) ?? col, v);
          if (label !== null) return label;
          return renderCellValue(v);
        },
      })),
    );
    if (!hideDueDate && isFixedColumnVisible('due_date')) {
      cols.push({
        id: 'due_date',
        label: 'Due date',
        render: (e: PipelineListEntity) => <DueDateCell value={e.due_date} />,
      });
    }
    if (isFixedColumnVisible('state')) {
      cols.push({
        id: 'state',
        label: labels.state,
        render: (e) => {
          const node = model.stateById.get(e.current_state);
          if (node) {
            return (
              <span
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-medium leading-5',
                  node.accent.badge,
                )}
              >
                <span className={cn('h-1.5 w-1.5 rounded-full', node.accent.dot)} />
                {node.label}
              </span>
            );
          }
          return e.current_state ? (
            <span className="inline-flex items-center gap-1.5 rounded-md border border-border bg-muted/50 px-2 py-0.5 text-[11px] font-medium leading-5 text-muted-foreground">
              <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/70" />
              {resolveStateLabel(e.current_state)}
            </span>
          ) : (
            <span className="text-muted-foreground/45">—</span>
          );
        },
      });
    }
    if (showAssignee && isFixedColumnVisible('assignee')) {
      cols.push({
        id: 'assignee',
        label: 'Owner',
        sortKey: null,
        render: (e) =>
          e.assignee_name && e.assignee_id ? (
            <span className="inline-flex min-w-0 items-center gap-2">
              <span
                className={cn(
                  'inline-flex h-6 w-6 flex-none items-center justify-center rounded-full text-[10px] font-semibold text-white',
                  getAvatarColorClass(e.assignee_id),
                )}
              >
                {getInitials(e.assignee_name)}
              </span>
              <span className="truncate text-[13px] text-foreground/80">{e.assignee_name}</span>
            </span>
          ) : (
            <span className="text-[12px] text-muted-foreground/60">Unassigned</span>
          ),
      });
    }
    if (showCreated && isFixedColumnVisible('created')) {
      cols.push({
        id: 'created',
        label: labels.created,
        render: (e) => (
          <span className="whitespace-nowrap text-[12px] tabular-nums text-muted-foreground">
            {formatDate(e.created_at)}
          </span>
        ),
      });
    }
    // Apply the saved org-wide order.
    const byId = new Map(cols.map((c) => [c.id, c]));
    return applyColumnOrder(
      cols.map((c) => c.id),
      order,
    ).map((id) => byId.get(id)!);
  }, [controller, effectiveFieldIds, hideDueDate, labels, model.entityType, model.stateById, order, resolveFieldMeta, showAssignee, showCreated, visibleColumns]);

  // Totals span the whole filtered set, so the threshold is the match count,
  // not this page's row count — the last page of 21 records still totals 21.
  const summaryRow = useMemo<Record<string, ReactNode> | undefined>(() => {
    if (!fieldTotals || totalCount < MIN_ROWS_FOR_SUMMARY) return undefined;
    const summed = columns.filter((col) => col.id in fieldTotals);
    if (summed.length === 0) return undefined;
    const cells: Record<string, ReactNode> = {};
    for (const col of summed) {
      cells[col.id] = <SummaryTotalCell total={fieldTotals[col.id]} />;
    }
    const labelColumn = columns.find((col) => !(col.id in fieldTotals));
    if (labelColumn) {
      cells[labelColumn.id] = (
        <span className="whitespace-nowrap font-normal text-muted-foreground">
          {`Σ · ${totalCount.toLocaleString()} records`}
        </span>
      );
    }
    return cells;
  }, [fieldTotals, totalCount, columns]);

  const pageCount = Math.max(1, Math.ceil(totalCount / pageSize));

  return (
    <Card
      // `max-h-full` rather than `h-full`: the card grows to the space available
      // for a long list, but shrinks to fit a short one instead of trailing
      // empty space under the pagination bar.
      className="flex max-h-full min-h-0 flex-col overflow-hidden rounded-xl border border-border/80 bg-card shadow-crisp"
      padding="none"
    >
      <PipelineListToolbar
        filteredCount={totalCount}
        totalCount={totalCount}
        entityType={model.entityType}
        search={search}
        onSearchChange={setSearch}
        showSearch={showSearch}
        stateFilter={stateFilter}
        onStateFilterChange={setStateFilter}
        states={stateOptions ?? model.states}
        entityTypes={entityTypes}
        entityTypeFilter={entityTypeFilter}
        onEntityTypeFilterChange={onEntityTypeFilterChange}
        identifierFilter={identifierFilter}
        onIdentifierFilterChange={setIdentifierFilter}
        identifierOptions={identifierOptions}
      >
        {allFields.length > 0 && (
          <ColumnVisibilityMenu
            fields={allFields}
            selectedIds={effectiveFieldIds}
            visibleCount={effectiveFieldIds.length}
            onToggle={toggleField}
          />
        )}
      </PipelineListToolbar>

      {enableBulkActions && (
        <BulkActionBar
          selected={bulk.selected}
          model={model}
          canDelete={canDelete}
          busy={bulk.busy}
          onClear={bulk.clear}
          onTransition={bulk.transition}
          onDelete={bulk.remove}
        />
      )}

      <PipelineListTable
        rows={rows}
        columns={columns}
        sort={sort}
        onToggleSort={toggleSort}
        onReorder={(ids) => void setOrder(ids)}
        onEntityClick={onEntityClick}
        enableRowTransitions={enableRowTransitions}
        onTransitionExecuted={onTransitionExecuted}
        selectable={enableBulkActions}
        selectedEntityIds={bulk.selectedIds}
        onSelectedChange={bulk.setSelected}
        summaryRow={summaryRow}
        pagination={
          totalCount > pageSize ? (
    
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border/70 bg-muted/10 px-4 py-2.5 text-xs text-muted-foreground">
              <span className="tabular-nums">
                {page * pageSize + 1}–{Math.min((page + 1) * pageSize, totalCount)} of {totalCount}
              </span>
              <Pagination className="mx-0 w-auto justify-end">
                <PaginationContent>
                  <PaginationItem>
                    <PaginationPrevious
                      aria-disabled={page === 0}
                      className={cn(page === 0 ? 'pointer-events-none opacity-40' : 'cursor-pointer')}
                      onClick={() => setPage((current) => Math.max(0, current - 1))}
                    />
                  </PaginationItem>
                  {buildPageItems(page, pageCount).map((item, index) =>
                    item === 'ellipsis' ? (
                      <PaginationItem key={`ellipsis-${index}`}>
                        <PaginationEllipsis />
                      </PaginationItem>
                    ) : (
                      <PaginationItem key={item}>
                        <PaginationLink
                          isActive={item === page}
                          className="cursor-pointer tabular-nums"
                          onClick={() => setPage(item)}
                        >
                          {item + 1}
                        </PaginationLink>
                      </PaginationItem>
                    ),
                  )}
                  <PaginationItem>
                    <PaginationNext
                      aria-disabled={page >= pageCount - 1}
                      className={cn(page >= pageCount - 1 ? 'pointer-events-none opacity-40' : 'cursor-pointer')}
                      onClick={() => setPage((current) => Math.min(pageCount - 1, current + 1))}
                    />
                  </PaginationItem>
                </PaginationContent>
              </Pagination>
            </div>
          ) : undefined
        }
      />
    </Card>
  );
}
