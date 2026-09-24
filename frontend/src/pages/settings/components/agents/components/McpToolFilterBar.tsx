import { Search, X } from 'lucide-react';

import { SegmentedControl } from '../../../../../core/components/SegmentedControl';

export type McpToolTypeFilter = 'all' | 'read_only' | 'mutating';

const TYPE_OPTIONS = [
  { value: 'all' as const, label: 'All' },
  { value: 'read_only' as const, label: 'Read-only' },
  { value: 'mutating' as const, label: 'Mutating' },
];

interface McpToolFilterBarProps {
  search: string;
  onSearchChange: (value: string) => void;
  typeFilter: McpToolTypeFilter;
  onTypeFilterChange: (value: McpToolTypeFilter) => void;
  visibleCount: number;
  totalCount: number;
}

/** Search + read-only/mutating filter for the tool catalog, with a live match count. */
export default function McpToolFilterBar({
  search,
  onSearchChange,
  typeFilter,
  onTypeFilterChange,
  visibleCount,
  totalCount,
}: McpToolFilterBarProps) {
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="relative flex-1 sm:max-w-sm">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          value={search}
          onChange={e => onSearchChange(e.target.value)}
          placeholder="Search tools by name or description…"
          className="h-9 w-full rounded-md border border-border bg-background py-2 pl-9 pr-8 text-sm shadow-sm placeholder:text-muted-foreground focus:border-cobalt focus:outline-none focus:ring-2 focus:ring-cobalt/30"
        />
        {search && (
          <button
            type="button"
            onClick={() => onSearchChange('')}
            aria-label="Clear search"
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      <div className="flex items-center gap-3">
        <SegmentedControl size="sm" options={TYPE_OPTIONS} value={typeFilter} onChange={onTypeFilterChange} />
        <span className="whitespace-nowrap text-xs text-muted-foreground">
          {visibleCount} of {totalCount} tools
        </span>
      </div>
    </div>
  );
}
