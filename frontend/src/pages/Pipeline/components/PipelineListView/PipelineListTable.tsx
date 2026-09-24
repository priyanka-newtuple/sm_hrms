import type { ReactNode } from 'react';
import type { ColumnDef, OnChangeFn, SortingState } from '@tanstack/react-table';
import { SearchX } from 'lucide-react';
import { Checkbox } from '@/components/ui/checkbox';
import { DataTable } from '@/core/components/DataTable';
import type { PipelineListEntity } from '@/shared/types/pipeline';
import type { ColumnDescriptor, ListSort, SortKey } from './types';
import TransitionActions from '@/shared/components/TransitionActions';

interface PipelineListTableProps {
  rows: PipelineListEntity[];
  /** Ordered, reorderable columns. */
  columns: ColumnDescriptor[];
  sort: ListSort;
  onToggleSort: (key: SortKey) => void;
  /** Persist a new column order (array of column ids). */
  onReorder: (ids: string[]) => void;
  onEntityClick?: (entityId: string, workflowId?: string) => void;
  enableRowTransitions?: boolean;
  onTransitionExecuted?: () => void;
  /** Page controls, pinned to the table's bottom edge. */
  pagination?: ReactNode;
  /** Pinned totals row, keyed by column id. Omitted when there is nothing to total. */
  summaryRow?: Record<string, ReactNode>;
  /** Show a leading checkbox column for bulk actions. */
  selectable?: boolean;
  selectedEntityIds?: Set<string>;
  onSelectedChange?: (entity: PipelineListEntity, selected: boolean) => void;
}

/** A descriptor's sort key: its own `id` by default, `null` to disable sorting. */
function sortKeyOf(col: ColumnDescriptor): SortKey | null {
  return col.sortKey === undefined ? col.id : col.sortKey;
}

function rowKey(entity: PipelineListEntity): string {
  return entity.state_id ?? `${entity.entity_id}:${entity.workflow_id ?? 'unenrolled'}`;
}

/** Descriptor-driven list with drag-to-reorder column headers. */
export default function PipelineListTable({
  rows,
  columns,
  sort,
  onToggleSort,
  onReorder,
  onEntityClick,
  enableRowTransitions = false,
  onTransitionExecuted,
  pagination,
  summaryRow,
  selectable = false,
  selectedEntityIds = new Set(),
  onSelectedChange,
}: PipelineListTableProps) {
  const tableColumns: ColumnDef<PipelineListEntity, unknown>[] = columns.map((col) => ({
    id: col.id,
    header: col.label,
    enableSorting: sortKeyOf(col) != null,
    // A column only counts as sortable once it has an accessor, and these
    // descriptors expose a renderer rather than a value. Ordering happens in the
    // list hook (`manualSorting`), so the accessor exists purely to enable the
    // header's sort control.
    accessorFn: () => null,
    cell: ({ row }) => col.render(row.original),
    meta: { align: col.align },
  }));

  if (selectable) {
    const selectedOnPage = rows.filter((entity) => selectedEntityIds.has(entity.entity_id)).length;
    const allOnPageSelected = rows.length > 0 && selectedOnPage === rows.length;

    tableColumns.unshift({
      id: 'select',
      enableSorting: false,
      header: () => (
        <Checkbox
          checked={allOnPageSelected}
          indeterminate={selectedOnPage > 0 && !allOnPageSelected}
          onCheckedChange={(checked) =>
            rows.forEach((entity) => onSelectedChange?.(entity, checked === true))
          }
          aria-label="Select all entities on this page"
        />
      ),
      cell: ({ row }) => (
        <span onClick={(event) => event.stopPropagation()}>
          <Checkbox
            checked={selectedEntityIds.has(row.original.entity_id)}
            onCheckedChange={(checked) => onSelectedChange?.(row.original, checked === true)}
            aria-label={`Select ${row.original.entity_id}`}
          />
        </span>
      ),
      meta: { sticky: 'left', width: '3rem', noReorder: true },
    });
  }

  if (enableRowTransitions) {
    tableColumns.push({
      id: 'transition',
      header: 'Transition',
      enableSorting: false,
      cell: ({ row }) => (
        <TransitionActions
          variant="menu"
          showTerminal
          entityId={row.original.entity_id}
          workflowId={row.original.workflow_id}
          availableTransitions={row.original.transition_options}
          onExecuted={onTransitionExecuted}
        />
      ),
      meta: { align: 'right', sticky: 'right', noReorder: true },
    });
  }

  // Sorting lives in the list hook (it also drives the server query), so the
  // table only reflects it: map the active sort key back to its column, and
  // translate any header click into the hook's own asc/desc toggle.
  const activeColumnId = columns.find((col) => {
    const key = sortKeyOf(col);
    return key != null && key === sort.key;
  })?.id;

  const sorting: SortingState = activeColumnId
    ? [{ id: activeColumnId, desc: sort.dir === 'desc' }]
    : [];

  const handleSortingChange: OnChangeFn<SortingState> = (updater) => {
    const next = typeof updater === 'function' ? updater(sorting) : updater;
    // Falls back to the current column: the table's third click clears sorting,
    // but this list only ever cycles asc/desc.
    const clickedId = next[0]?.id ?? activeColumnId;
    const clicked = columns.find((col) => col.id === clickedId);
    const key = clicked ? sortKeyOf(clicked) : null;
    if (key != null) onToggleSort(key);
  };

  const columnOrder = tableColumns.map((col) => col.id as string);

  // Pinned columns (selection, transition) are table chrome, not fields — they
  // must never reach the org-wide persisted field order.
  const pinnedIds = new Set(
    tableColumns.filter((col) => col.meta?.noReorder).map((col) => col.id as string),
  );

  const handleColumnOrderChange: OnChangeFn<string[]> = (updater) => {
    const next = typeof updater === 'function' ? updater(columnOrder) : updater;
    onReorder(next.filter((id) => !pinnedIds.has(id)));
  };

  return (
    <DataTable
      label="Pipeline entities"
      data={rows}
      columns={tableColumns}
      getRowId={rowKey}
      manualSorting
      sorting={sorting}
      onSortingChange={handleSortingChange}
      enableColumnReorder
      columnOrder={columnOrder}
      onColumnOrderChange={handleColumnOrderChange}
      onRowClick={
        onEntityClick ? (entity) => onEntityClick(entity.entity_id, entity.workflow_id) : undefined
      }
      paginationBar={pagination}
      summaryRow={summaryRow}
      maxHeight="100%"
      className="min-h-0 flex-1"
      framed={false}
      emptyState={{
        icon: <SearchX />,
        title: 'No matching entities',
        description: 'Try adjusting your search or filters.',
      }}
    />
  );
}
