import { Search, SlidersHorizontal } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuLabel,
  DropdownMenuCheckboxItem,
  DropdownMenuSeparator,
  DropdownMenuItem,
} from '@/components/ui/dropdown-menu';

export type StatusFilter = 'all' | 'active' | 'draft';

export interface OwnerOption {
  id: string;
  name: string;
}

interface FunnelListFilterBarProps {
  statusFilter: StatusFilter;
  onStatusFilterChange: (filter: StatusFilter) => void;
  search: string;
  onSearchChange: (search: string) => void;
  counts: Record<StatusFilter, number>;
  owners: OwnerOption[];
  ownerFilter: Set<string>;
  onOwnerFilterChange: (owners: Set<string>) => void;
  versions: number[];
  versionFilter: Set<number>;
  onVersionFilterChange: (versions: Set<number>) => void;
}

const filterTabs: { id: StatusFilter; label: string }[] = [
  { id: 'all',    label: 'All' },
  { id: 'active', label: 'Active' },
  { id: 'draft',  label: 'Draft' },
];

/**
 * Toggles a value in an immutable Set, returning a new Set instance.
 *
 * @param set - the source Set to toggle within.
 * @param value - the value to add or remove.
 * @returns a new Set with the value toggled.
 */
function toggleInSet<T>(set: Set<T>, value: T): Set<T> {
  const next = new Set(set);
  if (next.has(value)) {
    next.delete(value);
  } else {
    next.add(value);
  }
  return next;
}

/**
 * Filter bar for the workflow (funnel) list page.
 *
 * Renders a segmented status tab group (All / Active / Draft) with live
 * counts, a search input for filtering workflows by name, and a Filters
 * dropdown for narrowing by owner and version. Purely controlled — state
 * lives in the parent.
 *
 * @param props - {@link FunnelListFilterBarProps}
 * @param props.statusFilter - currently selected status tab.
 * @param props.onStatusFilterChange - called when user picks a different status tab.
 * @param props.search - current search query string.
 * @param props.onSearchChange - called on every search input change.
 * @param props.counts - record of workflow counts per status, used for tab badges.
 * @param props.owners - distinct owners available to filter by, derived from the current record set.
 * @param props.ownerFilter - currently selected owner ids.
 * @param props.onOwnerFilterChange - called with the updated owner id set.
 * @param props.versions - distinct versions available to filter by, derived from the current record set.
 * @param props.versionFilter - currently selected versions.
 * @param props.onVersionFilterChange - called with the updated version set.
 */
export default function FunnelListFilterBar({
  statusFilter,
  onStatusFilterChange,
  search,
  onSearchChange,
  counts,
  owners,
  ownerFilter,
  onOwnerFilterChange,
  versions,
  versionFilter,
  onVersionFilterChange,
}: FunnelListFilterBarProps) {
  const activeFilterCount = ownerFilter.size + versionFilter.size;

  return (
    <div className="flex items-center justify-between gap-3 mb-5">
      <div className="flex items-center gap-1 rounded-xl border border-border bg-muted/30 p-1">
        {filterTabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => onStatusFilterChange(tab.id)}
            className={cn(
              'flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors',
              statusFilter === tab.id
                ? 'bg-background shadow-sm text-foreground'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {tab.label}
            <span className={cn(
              'text-xs tabular-nums',
              statusFilter === tab.id ? 'text-foreground' : 'text-muted-foreground/70',
            )}>
              {counts[tab.id]}
            </span>
          </button>
        ))}
      </div>

      <div className="flex items-center gap-2">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
          <input
            type="text"
            placeholder="Search workflows..."
            value={search}
            onChange={e => onSearchChange(e.target.value)}
            className="h-9 w-56 rounded-lg border border-border bg-background pl-9 pr-3 text-sm placeholder:text-muted-foreground/60 focus:outline-none focus:ring-2 focus:ring-ring/30"
          />
        </div>

        <DropdownMenu>
          <DropdownMenuTrigger
            className={cn(
              'flex items-center gap-2 rounded-lg border border-border bg-background px-3 py-2 text-sm font-medium transition-colors',
              activeFilterCount > 0 ? 'text-foreground' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            <SlidersHorizontal className="w-4 h-4" />
            Filters
            {activeFilterCount > 0 && (
              <span className="flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-semibold text-primary-foreground">
                {activeFilterCount}
              </span>
            )}
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuGroup>
              <DropdownMenuLabel>Owner</DropdownMenuLabel>
              {owners.length === 0 ? (
                <div className="px-2 py-1.5 text-xs text-muted-foreground">No owners yet</div>
              ) : (
                owners.map(owner => (
                  <DropdownMenuCheckboxItem
                    key={owner.id}
                    checked={ownerFilter.has(owner.id)}
                    onCheckedChange={() => onOwnerFilterChange(toggleInSet(ownerFilter, owner.id))}
                  >
                    {owner.name}
                  </DropdownMenuCheckboxItem>
                ))
              )}
            </DropdownMenuGroup>

            <DropdownMenuSeparator />

            <DropdownMenuGroup>
              <DropdownMenuLabel>Version</DropdownMenuLabel>
              {versions.length === 0 ? (
                <div className="px-2 py-1.5 text-xs text-muted-foreground">No versions yet</div>
              ) : (
                versions.map(version => (
                  <DropdownMenuCheckboxItem
                    key={version}
                    checked={versionFilter.has(version)}
                    onCheckedChange={() => onVersionFilterChange(toggleInSet(versionFilter, version))}
                  >
                    {version === 0 ? 'Draft' : `v${version}`}
                  </DropdownMenuCheckboxItem>
                ))
              )}
            </DropdownMenuGroup>

            {activeFilterCount > 0 && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onClick={() => {
                    onOwnerFilterChange(new Set());
                    onVersionFilterChange(new Set());
                  }}
                >
                  Clear filters
                </DropdownMenuItem>
              </>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}
