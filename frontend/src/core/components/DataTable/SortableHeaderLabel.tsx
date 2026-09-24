import type { ReactNode } from 'react';
import type { Column } from '@tanstack/react-table';
import { ChevronDown, ChevronUp, ChevronsUpDown, Sparkles } from 'lucide-react';

/**
 * Header label with the column's type glyph and, when the column is sortable,
 * a sort toggle. `<DataTable>` wraps plain string headers in this automatically;
 * use it directly only for custom header markup.
 */
export function SortableHeaderLabel<T>({
  column,
  icon,
  children,
  enrichable,
}: {
  column: Column<T, unknown>;
  icon?: ReactNode;
  children: ReactNode;
  enrichable?: boolean;
}) {
  const sortable = column.getCanSort();
  const sorted = column.getIsSorted();

  const content = (
    <>
      {icon && (
        <span className="text-muted-foreground/70 [&_svg]:size-3.5 [&_svg]:[stroke-width:1.75]">
          {icon}
        </span>
      )}
      <span className="truncate">{children}</span>
      <span className="ml-auto flex shrink-0 items-center gap-1">
        {sortable &&
          (sorted === 'asc' ? (
            <ChevronUp className="size-3.5 text-foreground" />
          ) : sorted === 'desc' ? (
            <ChevronDown className="size-3.5 text-foreground" />
          ) : (
            <ChevronsUpDown className="size-3.5 opacity-40" />
          ))}
        {enrichable && <Sparkles className="size-3.5 text-violet-400/70" />}
      </span>
    </>
  );

  if (!sortable) {
    return <span className="flex w-full items-center gap-1.5">{content}</span>;
  }

  return (
    <button
      type="button"
      onClick={column.getToggleSortingHandler()}
      aria-label={`Sort by ${typeof children === 'string' ? children : column.id}`}
      className="flex w-full cursor-pointer items-center gap-1.5 rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
    >
      {content}
    </button>
  );
}
