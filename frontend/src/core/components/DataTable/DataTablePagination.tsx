import type { Table } from '@tanstack/react-table';

import type { ServerPagination } from './types';

function PaginationBar({
  label,
  canPrevious,
  canNext,
  onPrevious,
  onNext,
}: {
  label: string;
  canPrevious: boolean;
  canNext: boolean;
  onPrevious: () => void;
  onNext: () => void;
}) {
  return (
    // `sticky bottom-0` keeps the bar on screen even when the table is left
    // unbounded (`maxHeight="none"`) and the page itself does the scrolling.
    <div className="sticky bottom-0 z-10 flex shrink-0 items-center justify-between border-t border-border/60 bg-background px-3 py-2 text-[12px] text-muted-foreground">
      <span>{label}</span>
      <div className="flex items-center gap-1">
        <button
          type="button"
          disabled={!canPrevious}
          onClick={onPrevious}
          className="h-7 cursor-pointer rounded-md border border-border/70 px-2.5 text-foreground/70 transition-colors hover:bg-muted disabled:cursor-default disabled:opacity-40"
        >
          Previous
        </button>
        <button
          type="button"
          disabled={!canNext}
          onClick={onNext}
          className="h-7 cursor-pointer rounded-md border border-border/70 px-2.5 text-foreground/70 transition-colors hover:bg-muted disabled:cursor-default disabled:opacity-40"
        >
          Next
        </button>
      </div>
    </div>
  );
}

function rangeLabel(from: number, to: number, total: number): string {
  return `${from}–${to} of ${total.toLocaleString()}`;
}

/** Pagination driven by the server: the parent owns offset and refetches. */
export function DataTablePagination({ total, limit, offset, onChange }: ServerPagination) {
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + limit, total);
  return (
    <PaginationBar
      label={rangeLabel(from, to, total)}
      canPrevious={offset > 0}
      canNext={to < total}
      onPrevious={() => onChange(Math.max(0, offset - limit))}
      onNext={() => onChange(offset + limit)}
    />
  );
}

/** Pagination over rows already in memory. */
export function DataTableClientPagination<T>({ table }: { table: Table<T> }) {
  const { pageIndex, pageSize } = table.getState().pagination;
  // Rows before the page slice — correct without depending on the filter feature.
  const total = table.getPrePaginationRowModel().rows.length;
  const from = total === 0 ? 0 : pageIndex * pageSize + 1;
  const to = Math.min((pageIndex + 1) * pageSize, total);
  return (
    <PaginationBar
      label={rangeLabel(from, to, total)}
      canPrevious={table.getCanPreviousPage()}
      canNext={table.getCanNextPage()}
      onPrevious={() => table.previousPage()}
      onNext={() => table.nextPage()}
    />
  );
}
