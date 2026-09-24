import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationNext,
  PaginationPrevious,
} from '@/components/ui/pagination';

interface BulkImportPaginationProps {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  noun?: string;
}

export default function BulkImportPagination({
  page,
  pageSize,
  total,
  onPageChange,
  noun = 'items',
}: BulkImportPaginationProps) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  if (total <= pageSize) return null;

  const first = page * pageSize + 1;
  const last = Math.min((page + 1) * pageSize, total);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border/70 bg-muted/10 px-4 py-2.5 text-xs text-muted-foreground">
      <span className="tabular-nums">
        {first} to {last} of {total} {noun}
      </span>
      <div className="flex items-center gap-3">
        <span className="tabular-nums">Page {page + 1} of {pageCount}</span>
        <Pagination className="mx-0 w-auto justify-end">
          <PaginationContent>
            <PaginationItem>
              <PaginationPrevious
                href="#"
                aria-disabled={page === 0}
                className={page === 0 ? 'pointer-events-none opacity-40' : 'cursor-pointer'}
                onClick={(event) => {
                  event.preventDefault();
                  onPageChange(Math.max(0, page - 1));
                }}
              />
            </PaginationItem>
            <PaginationItem>
              <PaginationNext
                href="#"
                aria-disabled={page >= pageCount - 1}
                className={page >= pageCount - 1 ? 'pointer-events-none opacity-40' : 'cursor-pointer'}
                onClick={(event) => {
                  event.preventDefault();
                  onPageChange(Math.min(pageCount - 1, page + 1));
                }}
              />
            </PaginationItem>
          </PaginationContent>
        </Pagination>
      </div>
    </div>
  );
}
