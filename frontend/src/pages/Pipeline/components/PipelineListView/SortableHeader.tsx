import { ChevronUp, ChevronDown, ChevronsUpDown } from 'lucide-react';
import type { ListSort, SortKey } from './types';

interface SortableHeaderProps {
  label: string;
  columnKey: SortKey;
  sort: ListSort;
  onToggle: (key: SortKey) => void;
}

/** A clickable table header that toggles sort direction for its column. */
export default function SortableHeader({ label, columnKey, sort, onToggle }: SortableHeaderProps) {
  const active = sort.key === columnKey;
  return (
    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
      <button
        type="button"
        onClick={() => onToggle(columnKey)}
        className="inline-flex items-center gap-1 uppercase tracking-[0.12em] hover:text-muted-foreground"
      >
        {label}
        {active ? (
          sort.dir === 'asc' ? (
            <ChevronUp className="h-3.5 w-3.5" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5" />
          )
        ) : (
          <ChevronsUpDown className="h-3.5 w-3.5 opacity-40" />
        )}
      </button>
    </th>
  );
}
