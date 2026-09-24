import type { ColumnMeta, Table } from '@tanstack/react-table';

import { cn } from '@/lib/utils';

export type DataTableColumnMeta = ColumnMeta<unknown, unknown>;

/** The table's column order, falling back to its natural leaf order. */
export function currentColumnOrder<T>(table: Table<T>): string[] {
  const order = table.getState().columnOrder;
  return order.length > 0 ? order : table.getAllLeafColumns().map((column) => column.id);
}

/** Column ids that may be dragged — pinned columns (selection, actions) stay put. */
export function reorderableIds<T>(table: Table<T>): string[] {
  return currentColumnOrder(table).filter(
    (id) => !(table.getColumn(id)?.columnDef.meta as DataTableColumnMeta | undefined)?.noReorder,
  );
}

const HIDE_BELOW: Record<NonNullable<DataTableColumnMeta['hideBelow']>, string> = {
  sm: 'hidden sm:table-cell',
  md: 'hidden md:table-cell',
  lg: 'hidden lg:table-cell',
};

/**
 * Layout classes a column's `meta` implies. Shared by header and body cells so
 * the two never drift apart.
 *
 * A pinned body cell uses `bg-inherit` so it picks up the row's own background
 * (hover, selected, or a `getRowClassName` tint) rather than punching an opaque
 * hole through it; a pinned header cell needs the solid header background so
 * rows don't show through as they scroll underneath.
 */
export function columnClasses(
  meta: DataTableColumnMeta | undefined,
  variant: 'head' | 'cell' = 'cell',
): string {
  if (!meta) return '';
  const pinnedBackground = variant === 'head' ? 'bg-background' : 'bg-inherit';
  return cn(
    (meta.align === 'right' || meta.numeric) && 'text-right',
    meta.numeric && 'tabular-nums',
    meta.hideBelow && HIDE_BELOW[meta.hideBelow],
    meta.sticky === 'left' && cn('sticky left-0 z-[1]', pinnedBackground),
    meta.sticky === 'right' && cn('sticky right-0 z-[1]', pinnedBackground),
  );
}
