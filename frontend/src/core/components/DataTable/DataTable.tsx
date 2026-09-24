import { useState } from 'react';
import {
  getCoreRowModel,
  getExpandedRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnOrderState,
  type RowSelectionState,
  type SortingState,
  type TableOptions,
} from '@tanstack/react-table';

import { cn } from '@/lib/utils';
import { Table, TableFooter, TableRow, TableCell } from '@/components/ui/table';

import { ColumnReorderProvider } from './ColumnReorderProvider';
import { DataTableBody } from './DataTableBody';
import { DataTableHeader } from './DataTableHeader';
import { DataTableClientPagination, DataTablePagination } from './DataTablePagination';
import type { DataTableProps } from './types';
import { columnClasses, type DataTableColumnMeta } from './utils';

const DENSITY = {
  comfortable: '[&_tbody_tr]:h-11 [&_tbody_td]:py-2',
  compact: '[&_tbody_tr]:h-9 [&_tbody_td]:py-1.5',
} as const;

/**
 * The platform's data table: an Attio-style grid over `@tanstack/react-table`.
 *
 * Presentational only — it never fetches. Sorting, selection and column order
 * are uncontrolled by default and become controlled as soon as the matching
 * state prop is supplied (which is also how server-driven tables opt in via
 * `manualSorting` / `serverPagination`).
 */
export function DataTable<T>({
  columns,
  data,
  getRowId,
  isLoading,
  emptyState,
  onRowClick,
  enableSorting = true,
  initialSorting,
  manualSorting,
  sorting,
  onSortingChange,
  enableRowSelection,
  rowSelection,
  onRowSelectionChange,
  clientPageSize,
  serverPagination,
  getRowClassName,
  renderExpanded,
  getRowCanExpand,
  stickyHeader = true,
  // Viewport-relative so tall screens show more rows, while the header stays
  // pinned and the pagination bar stays in view instead of below every row.
  maxHeight = '70vh',
  density = 'comfortable',
  zebra,
  columnDividers = true,
  toolbar,
  footerRow,
  summaryRow,
  paginationBar,
  enableColumnReorder,
  columnOrder,
  onColumnOrderChange,
  framed = true,
  className,
  label,
}: DataTableProps<T>) {
  const [internalSorting, setInternalSorting] = useState<SortingState>(initialSorting ?? []);
  const [internalSelection, setInternalSelection] = useState<RowSelectionState>({});
  const [internalColumnOrder, setInternalColumnOrder] = useState<ColumnOrderState>([]);

  const clientPaginated = Boolean(clientPageSize) && !serverPagination;

  const options: TableOptions<T> = {
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    state: {
      sorting: sorting ?? internalSorting,
      rowSelection: rowSelection ?? internalSelection,
      columnOrder: columnOrder ?? internalColumnOrder,
    },
    onSortingChange: onSortingChange ?? setInternalSorting,
    onRowSelectionChange: onRowSelectionChange ?? setInternalSelection,
    onColumnOrderChange: onColumnOrderChange ?? setInternalColumnOrder,
    enableSorting,
    manualSorting,
    enableRowSelection,
    manualPagination: Boolean(serverPagination),
  };

  if (getRowId) options.getRowId = (row) => getRowId(row);
  // Only attach the row models a table actually uses — each one costs work per render.
  if (enableSorting && !manualSorting) options.getSortedRowModel = getSortedRowModel();
  if (renderExpanded) {
    options.getExpandedRowModel = getExpandedRowModel();
    options.getRowCanExpand = getRowCanExpand ? (row) => getRowCanExpand(row.original) : () => true;
  }
  if (clientPaginated) {
    options.getPaginationRowModel = getPaginationRowModel();
    options.initialState = { pagination: { pageIndex: 0, pageSize: clientPageSize } };
  }

  const table = useReactTable(options);

  const content = (
    <>
      <Table
        aria-label={label}
        // Sizes to its rows rather than growing, so a short table doesn't leave
        // a gap above the pagination bar. `min-h-0` lets it shrink — and so
        // scroll — once the rows exceed the table's max height.
        containerClassName="min-h-0"
        className={cn(
          DENSITY[density],
          !columnDividers && '[&_th]:border-r-0 [&_td]:border-r-0',
        )}
      >
        <DataTableHeader
          table={table}
          stickyHeader={stickyHeader}
          enableColumnReorder={enableColumnReorder}
        />

        <DataTableBody
          table={table}
          onRowClick={onRowClick}
          getRowClassName={getRowClassName}
          renderExpanded={renderExpanded}
          isLoading={isLoading}
          emptyState={emptyState}
          zebra={zebra}
        />

        {(footerRow || summaryRow) && (
          <TableFooter>
            {summaryRow && (
              <TableRow className="hover:bg-transparent">
                {table.getVisibleLeafColumns().map((column) => {
                  const meta = column.columnDef.meta as DataTableColumnMeta | undefined;
                  return (
                    <TableCell
                      key={column.id}
                      className={cn(
                        // Same alignment/pinning/responsive rules the header and
                        // body cells get, so a pinned column stays pinned here
                        // too instead of the totals sliding out from under it.
                        columnClasses(meta),
                        // Opaque, not `bg-muted/10`: this row is sticky, so a
                        // translucent fill lets scrolling rows show through.
                        // `border-collapse` drops a detached sticky cell's own
                        // border, so the top rule is an inset shadow, as in the header.
                        'sticky bottom-0 z-10 font-medium tabular-nums text-foreground',
                        'bg-[color-mix(in_oklab,var(--muted)_10%,var(--background))]',
                        'shadow-[inset_0_1px_0_var(--border)]',
                        meta?.sticky && 'z-20',
                      )}
                    >
                      {summaryRow[column.id] ?? null}
                    </TableCell>
                  );
                })}
              </TableRow>
            )}
            {footerRow && (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={table.getVisibleLeafColumns().length} className="border-r-0">
                  {footerRow}
                </TableCell>
              </TableRow>
            )}
          </TableFooter>
        )}
      </Table>
    </>
  );

  return (
    // A bounded column: toolbar and pagination hold the top and bottom edges
    // while the rows scroll between them, so both stay on screen.
    <div
      className={cn(
        'flex w-full flex-col bg-background',
        framed && 'overflow-hidden rounded-lg border border-border/70',
        className,
      )}
      style={maxHeight === 'none' ? undefined : { maxHeight }}
    >
      {toolbar}

      {enableColumnReorder ? (
        <ColumnReorderProvider table={table}>{content}</ColumnReorderProvider>
      ) : (
        content
      )}

      {paginationBar && (
        <div className="sticky bottom-0 z-10 shrink-0 bg-background">{paginationBar}</div>
      )}
      {serverPagination && <DataTablePagination {...serverPagination} />}
      {clientPaginated && <DataTableClientPagination table={table} />}
    </div>
  );
}
