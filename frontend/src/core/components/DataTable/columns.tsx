import type { ReactNode } from 'react';
import type { ColumnDef } from '@tanstack/react-table';

import { Checkbox } from '@/components/ui/checkbox';
import { cn } from '@/lib/utils';

/**
 * Column factories and header pieces shared by every data table. Build column
 * definitions with these instead of hand-rolling selection/action columns.
 */

/** The platform checkbox, plus the indeterminate treatment the header needs. */
const CHECKBOX_CLASS = cn(
  'data-[indeterminate]:border-primary data-[indeterminate]:bg-primary data-[indeterminate]:text-primary-foreground',
  '[&[data-indeterminate]_svg]:hidden',
  'data-[indeterminate]:before:h-0.5 data-[indeterminate]:before:w-2 data-[indeterminate]:before:rounded-full data-[indeterminate]:before:bg-current',
);

/** Leading checkbox column: select-all-page in the header, per-row below. */
export function selectionColumn<T>(): ColumnDef<T, unknown> {
  return {
    id: 'select',
    enableSorting: false,
    header: ({ table }) => (
      <Checkbox
        aria-label="Select all rows on this page"
        className={CHECKBOX_CLASS}
        checked={table.getIsAllPageRowsSelected()}
        indeterminate={table.getIsSomePageRowsSelected() && !table.getIsAllPageRowsSelected()}
        onCheckedChange={(checked) => table.toggleAllPageRowsSelected(checked)}
      />
    ),
    cell: ({ row }) => (
      // Stop propagation so ticking a row doesn't also trigger onRowClick.
      <span onClick={(event) => event.stopPropagation()}>
        <Checkbox
          aria-label="Select row"
          className={CHECKBOX_CLASS}
          checked={row.getIsSelected()}
          onCheckedChange={(checked) => row.toggleSelected(checked)}
        />
      </span>
    ),
    meta: { sticky: 'left', width: '2.25rem', noReorder: true },
  };
}

/**
 * Trailing actions column. On pointer devices the actions stay hidden until the
 * row is hovered or something inside takes focus, so the grid reads clean at
 * rest. Where hover doesn't exist (touch) they are always visible — otherwise
 * they would be unreachable.
 */
export function actionsColumn<T>({
  render,
  width = '5rem',
  alwaysVisible,
}: {
  render: (row: T) => ReactNode;
  width?: string;
  /** Keep the actions visible at rest instead of revealing them on hover. */
  alwaysVisible?: boolean;
}): ColumnDef<T, unknown> {
  return {
    id: 'actions',
    enableSorting: false,
    header: () => null,
    cell: ({ row }) => (
      <div
        className={cn(
          'flex items-center justify-end gap-0.5 transition-opacity focus-within:opacity-100',
          !alwaysVisible &&
            '[@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover/row:opacity-100',
        )}
        onClick={(event) => event.stopPropagation()}
      >
        {render(row.original)}
      </div>
    ),
    meta: { align: 'right', sticky: 'right', width, noReorder: true },
  };
}
