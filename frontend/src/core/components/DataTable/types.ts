import type { ReactNode } from 'react';
import type {
  ColumnDef,
  ColumnOrderState,
  OnChangeFn,
  RowData,
  RowSelectionState,
  SortingState,
} from '@tanstack/react-table';

/**
 * Presentation hints a column can carry. Read by `<DataTable>` when rendering
 * header and body cells — keeps layout concerns on the column definition
 * instead of leaking into every consumer's JSX.
 */
declare module '@tanstack/react-table' {
  // The generics mirror the upstream interface signature; they are unused here
  // because these are pure presentation flags.
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData extends RowData, TValue> {
    /** Horizontal alignment of header + cell content. */
    align?: 'left' | 'right';
    /** Numeric column: right-aligned with tabular figures. */
    numeric?: boolean;
    /** Pin the cell against the edge while the grid scrolls horizontally. */
    sticky?: 'left' | 'right';
    /** Hide the column below this breakpoint. */
    hideBelow?: 'sm' | 'md' | 'lg';
    /** Small type glyph rendered left of the header label. */
    headerIcon?: ReactNode;
    /** Show the decorative enrichment sparkle in the header. */
    enrichable?: boolean;
    /** Exclude from drag-to-reorder (pinned columns: selection, actions). */
    noReorder?: boolean;
    /** Fixed column width (CSS length). */
    width?: string;
  }
}

export type EmptyStateConfig = {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
};

export type ServerPagination = {
  total: number;
  limit: number;
  offset: number;
  onChange: (offset: number) => void;
};

export type DataTableProps<T> = {
  columns: ColumnDef<T, unknown>[];
  data: T[];
  /** Stable row id; falls back to the row index when omitted. */
  getRowId?: (row: T) => string;

  isLoading?: boolean;
  /** Rendered when there are no rows. */
  emptyState?: ReactNode | EmptyStateConfig;

  onRowClick?: (row: T) => void;

  enableSorting?: boolean;
  /** Sort applied on first render while the table owns its own sort state. */
  initialSorting?: SortingState;
  /** Sorting handled upstream (server); pair with `sorting` + `onSortingChange`. */
  manualSorting?: boolean;
  sorting?: SortingState;
  onSortingChange?: OnChangeFn<SortingState>;

  enableRowSelection?: boolean;
  rowSelection?: RowSelectionState;
  onRowSelectionChange?: OnChangeFn<RowSelectionState>;

  /** Client-side pagination with this page size. Ignored if `serverPagination` is set. */
  clientPageSize?: number;
  serverPagination?: ServerPagination;

  /** Extra classes per row — for data-driven row tinting. */
  getRowClassName?: (row: T) => string | undefined;
  /** Content rendered in a full-width row beneath an expanded row. */
  renderExpanded?: (row: T) => ReactNode;
  getRowCanExpand?: (row: T) => boolean;

  /** Pin the header while rows scroll. On by default. */
  stickyHeader?: boolean;
  /**
   * Caps the scrolling row area (any CSS length). Long tables scroll their rows
   * instead of the page, which keeps the header and the pagination bar in view.
   * Pass `'none'` to let the table grow to its full height.
   */
  maxHeight?: string;
  density?: 'comfortable' | 'compact';
  zebra?: boolean;
  /** Vertical dividers between columns (the grid look). Defaults to true. */
  columnDividers?: boolean;

  /** Slot above the table — filters, search, bulk actions. */
  toolbar?: ReactNode;
  /** Slot below the body — counts / aggregations, as one merged cell. */
  footerRow?: ReactNode;
  /**
   * Pinned summary row, keyed by column id — one cell per visible column,
   * unlike `footerRow`'s single merged cell. Columns with no entry render
   * empty. Keyed rather than positional so it survives column reordering.
   */
  summaryRow?: Record<string, ReactNode>;
  /**
   * Custom pagination pinned to the table's bottom edge, for callers with their
   * own controls. Use instead of `serverPagination` / `clientPageSize`.
   */
  paginationBar?: ReactNode;

  enableColumnReorder?: boolean;
  columnOrder?: ColumnOrderState;
  onColumnOrderChange?: OnChangeFn<ColumnOrderState>;

  /** Draw the table's outer frame. Disable when a parent card already owns it. */
  framed?: boolean;
  className?: string;
  /** Accessible name for the table. */
  label?: string;
};
