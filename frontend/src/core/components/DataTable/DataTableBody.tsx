import { Fragment, type ReactNode } from 'react';
import { flexRender, type Table } from '@tanstack/react-table';

import { cn } from '@/lib/utils';
import { TableBody, TableCell, TableRow } from '@/components/ui/table';

import type { DataTableProps, EmptyStateConfig } from './types';
import { columnClasses, type DataTableColumnMeta } from './utils';

/**
 * Row backgrounds, all mixed against `--background` rather than expressed as an
 * alpha (`bg-muted/30`). A pinned cell inherits the row's background and paints
 * it a second time on top, so a translucent row colour would composite twice
 * and leave the sticky column visibly darker than the row it belongs to.
 * A `getRowClassName` tint should follow the same rule.
 */
const HOVER_ROW = 'hover:bg-[color-mix(in_srgb,var(--muted)_30%,var(--background))]';
// Written out in full — Tailwind scans source text, so a composed class name
// (`` `…${ZEBRA}` ``) would never be generated.
const ZEBRA_ROWS =
  '[&_tr[data-zebra=odd]]:bg-[color-mix(in_srgb,var(--muted)_20%,var(--background))]';

/** Brand-tinted selected row — the same accent language as the sidebar's active item. */
const SELECTED_ROW = 'bg-[color-mix(in_srgb,var(--primary)_6%,var(--background))]';

function isEmptyStateConfig(value: unknown): value is EmptyStateConfig {
  return typeof value === 'object' && value !== null && 'title' in value;
}

function EmptyRow({ colSpan, emptyState }: { colSpan: number; emptyState?: ReactNode | EmptyStateConfig }) {
  const content = isEmptyStateConfig(emptyState) ? (
    <div className="flex flex-col items-center gap-1.5 py-10 text-center">
      {emptyState.icon && (
        <span className="text-muted-foreground/50 [&_svg]:size-6 [&_svg]:[stroke-width:1.5]">
          {emptyState.icon}
        </span>
      )}
      <span className="text-sm font-medium text-foreground">{emptyState.title}</span>
      {emptyState.description && (
        <span className="text-[13px] text-muted-foreground">{emptyState.description}</span>
      )}
      {emptyState.action}
    </div>
  ) : (
    (emptyState ?? <div className="py-10 text-center text-sm text-muted-foreground">No rows</div>)
  );

  return (
    <TableRow className="hover:bg-transparent">
      <TableCell colSpan={colSpan} className="border-r-0">
        {content}
      </TableCell>
    </TableRow>
  );
}

function SkeletonRows({ colSpan, rows = 5 }: { colSpan: number; rows?: number }) {
  return (
    <>
      {Array.from({ length: rows }, (_, index) => (
        <TableRow key={index} className="hover:bg-transparent">
          <TableCell colSpan={colSpan} className="border-r-0">
            <div className="h-4 w-full animate-pulse rounded bg-muted" />
          </TableCell>
        </TableRow>
      ))}
    </>
  );
}

type Props<T> = Pick<
  DataTableProps<T>,
  'onRowClick' | 'getRowClassName' | 'renderExpanded' | 'isLoading' | 'emptyState' | 'zebra'
> & { table: Table<T> };

export function DataTableBody<T>({
  table,
  onRowClick,
  getRowClassName,
  renderExpanded,
  isLoading,
  emptyState,
  zebra,
}: Props<T>) {
  const rows = table.getRowModel().rows;
  const colSpan = table.getVisibleLeafColumns().length;

  if (isLoading) {
    return (
      <TableBody>
        <SkeletonRows colSpan={colSpan} />
      </TableBody>
    );
  }

  if (rows.length === 0) {
    return (
      <TableBody>
        <EmptyRow colSpan={colSpan} emptyState={emptyState} />
      </TableBody>
    );
  }

  return (
    <TableBody className={cn(zebra && ZEBRA_ROWS)}>
      {rows.map((row, index) => {
        const selected = row.getIsSelected();
        return (
          <Fragment key={row.id}>
            <TableRow
              data-zebra={index % 2 === 1 ? 'odd' : undefined}
              data-selected={selected || undefined}
              role={onRowClick ? 'button' : undefined}
              tabIndex={onRowClick ? 0 : undefined}
              onClick={onRowClick ? () => onRowClick(row.original) : undefined}
              onKeyDown={
                onRowClick
                  ? (event) => {
                      // Keydown bubbles, so a checkbox or menu trigger inside the
                      // row would otherwise open the row *and* have its own
                      // activation cancelled by the preventDefault below. Only the
                      // row itself is focusable, so anything else as the target
                      // means a nested control owns the key.
                      if (event.target !== event.currentTarget) return;
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        onRowClick(row.original);
                      }
                    }
                  : undefined
              }
              className={cn(
                // `group/row` drives the hover-revealed actions column.
                'group/row bg-background',
                onRowClick && 'cursor-pointer',
                selected ? SELECTED_ROW : HOVER_ROW,
                getRowClassName?.(row.original),
              )}
            >
              {row.getVisibleCells().map((cell) => {
                const meta = cell.column.columnDef.meta as DataTableColumnMeta | undefined;
                return (
                  <TableCell key={cell.id} className={columnClasses(meta)}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                );
              })}
            </TableRow>

            {renderExpanded && row.getIsExpanded() && (
              <TableRow className="bg-muted/20 hover:bg-muted/20">
                <TableCell colSpan={colSpan} className="border-r-0 p-0">
                  {renderExpanded(row.original)}
                </TableCell>
              </TableRow>
            )}
          </Fragment>
        );
      })}
    </TableBody>
  );
}
