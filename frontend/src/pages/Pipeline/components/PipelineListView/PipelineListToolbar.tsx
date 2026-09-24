import type { ReactNode } from 'react';
import { ListChecks, Search } from 'lucide-react';
import { resolveEntityTypeLabel } from '@/shared/utils/labels';

interface PipelineListToolbarProps {
  title?: string;
  icon?: ReactNode;
  filteredCount: number;
  totalCount: number;
  entityType: string;
  search: string;
  onSearchChange: (value: string) => void;
  showSearch?: boolean;
  stateFilter: string;
  onStateFilterChange: (value: string) => void;
  states: { id: string; label: string }[];
  /** optional entity-type filter (aggregated cross-workflow view) */
  entityTypes?: string[];
  entityTypeFilter?: string;
  onEntityTypeFilterChange?: (value: string) => void;
  identifierFilter: string;
  onIdentifierFilterChange: (value: string) => void;
  identifierOptions: string[];
  /** trailing controls (e.g. the column-visibility menu) */
  children?: ReactNode;
}

/** Header toolbar: title/count, search box, state filter, and a slot for extra controls. */
export default function PipelineListToolbar({
  title = 'Entities',
  icon,
  filteredCount,
  totalCount,
  entityType,
  search,
  onSearchChange,
  showSearch = true,
  stateFilter,
  onStateFilterChange,
  states,
  entityTypes,
  entityTypeFilter,
  onEntityTypeFilterChange,
  identifierFilter,
  onIdentifierFilterChange,
  identifierOptions,
  children,
}: PipelineListToolbarProps) {
  const selectClass =
    'h-8 max-w-44 cursor-pointer rounded-md border border-input bg-background px-2.5 text-xs text-foreground transition-colors hover:border-primary/30 hover:bg-primary/5 focus:border-primary/40 focus:outline-none focus:ring-2 focus:ring-primary/10';
  return (
    <div className="border-b border-border/70 bg-muted/10 px-4 py-3">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="inline-flex h-8 w-8 flex-none items-center justify-center rounded-lg bg-primary/10 text-primary">
            {icon ?? <ListChecks className="h-4 w-4" />}
          </span>
          <div className="min-w-0">
            <div className="text-sm font-semibold text-foreground">{title}</div>
            <p className="truncate text-[11px] text-muted-foreground">
              <span className="font-medium text-foreground/80">{filteredCount}</span> of {totalCount}{' '}
              {resolveEntityTypeLabel(entityType)} entities
            </p>
          </div>
          {children && <div className="ml-auto lg:ml-2">{children}</div>}
        </div>

        <div className="flex w-full flex-wrap items-center gap-2 lg:w-auto lg:justify-end">
          {showSearch && (
            <div className="relative min-w-44 flex-1 sm:flex-none">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground/70" />
              <input
                type="text"
                aria-label="Search entities"
                placeholder="Search entities..."
                value={search}
                onChange={(e) => onSearchChange(e.target.value)}
                className="h-8 w-full rounded-md border border-input bg-background pl-8 pr-3 text-xs text-foreground transition-colors placeholder:text-muted-foreground/65 hover:border-primary/30 focus:border-primary/40 focus:outline-none focus:ring-2 focus:ring-primary/10 sm:w-48"
              />
            </div>
          )}

          {entityTypes && entityTypes.length > 0 && onEntityTypeFilterChange && (
            <select
              aria-label="Filter by entity type"
              value={entityTypeFilter ?? ''}
              onChange={(e) => onEntityTypeFilterChange(e.target.value)}
              className={selectClass}
            >
              <option value="">All types</option>
              {entityTypes.map((t) => (
                <option key={t} value={t}>
                  {resolveEntityTypeLabel(t)}
                </option>
              ))}
            </select>
          )}

          <select
            aria-label="Filter by state"
            value={stateFilter}
            onChange={(e) => onStateFilterChange(e.target.value)}
            className={selectClass}
          >
            <option value="">All states</option>
            {states.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>

          {identifierOptions.length > 0 && (
            <select
              aria-label={`Filter by ${resolveEntityTypeLabel(entityType)}`}
              value={identifierFilter}
              onChange={(e) => onIdentifierFilterChange(e.target.value)}
              className={selectClass}
            >
              <option value="">All {resolveEntityTypeLabel(entityType)}</option>
              {identifierOptions.map((id) => (
                <option key={id} value={id}>
                  {id}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>
    </div>
  );
}
