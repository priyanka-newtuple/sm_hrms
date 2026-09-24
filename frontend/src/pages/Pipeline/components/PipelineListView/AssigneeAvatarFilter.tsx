import { useCallback, useMemo } from 'react';
import { User as UserIcon, Filter as FilterIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import { getInitials, getAvatarColorClass } from '@/core/utils';
import { UNASSIGNED_FILTER } from '../../hooks/useAssigneeFilter';
import { useAssigneeFilterFrequency } from '../../hooks/useAssigneeFilterFrequency';
import { AVATAR_BASE, type AssigneeEntry } from './assigneeAvatarStyles';
import AssigneeOverflowDropdown from './AssigneeOverflowDropdown';

interface AssigneeAvatarFilterProps {
  /** Distinct named assignees present on the board, alphabetically sorted. */
  options: AssigneeEntry[];
  /** Whether any entity currently has no assignee — adds an "Unassigned" entry. */
  hasUnassigned: boolean;
  selectedIds: string[];
  onToggle: (id: string) => void;
  onClear: () => void;
  currentUserId?: string;
  /** Avatars shown directly in the row before folding the rest into "+N". */
  maxAvatars?: number;
}

/** A single toggleable avatar circle within the filter row — clicking it
 *  toggles that person in/out of the assignee filter directly, without
 *  opening the overflow picker. */
function AssigneeAvatar({
  entry,
  selected,
  onClick,
}: {
  entry: AssigneeEntry;
  selected: boolean;
  onClick: () => void;
}) {
  const isUnassigned = entry.id === UNASSIGNED_FILTER;
  return (
    <button
      type="button"
      title={entry.name}
      aria-pressed={selected}
      aria-label={`Filter by ${entry.name}`}
      onClick={onClick}
      className={cn(
        AVATAR_BASE,
        isUnassigned ? 'bg-muted-foreground' : getAvatarColorClass(entry.id),
        selected && 'ring-2 ring-cobalt ring-offset-1',
      )}
    >
      {isUnassigned ? <UserIcon className="h-4 w-4" /> : getInitials(entry.name)}
    </button>
  );
}

/** Jira-style assignee filter: a row of clickable, overlapping avatar circles
 *  (click to toggle membership directly) plus a "+N" trigger that opens a
 *  full checkbox list — multi-select, OR-matched against each entity's
 *  assignee. Avatar overlap follows Magic UI's Avatar Circles pattern
 *  (-space-x overlap, bordered circles) rather than a bespoke one. */
export default function AssigneeAvatarFilter({
  options,
  hasUnassigned,
  selectedIds,
  onToggle,
  onClear,
  currentUserId,
  maxAvatars = 5,
}: AssigneeAvatarFilterProps) {
  const { getAll: getSelectionFrequency, recordSelection } = useAssigneeFilterFrequency();

  // Promote whoever this browser's user actually filters by most into the
  // visible avatar row — otherwise the same fixed slate (minus the pinned
  // "me" entry) always occupies those slots, and someone's 2-3 most-used
  // teammates can end up permanently stuck behind "+N" if they weren't
  // already near the front of the incoming (alphabetical) order.
  const entries = useMemo<AssigneeEntry[]>(() => {
    const withUnassigned = hasUnassigned
      ? [...options, { id: UNASSIGNED_FILTER, name: 'Unassigned' }]
      : options;
    const frequency = getSelectionFrequency();
    return [...withUnassigned].sort((a, b) => {
      if (a.id === currentUserId) return -1;
      if (b.id === currentUserId) return 1;
      return (frequency[b.id] ?? 0) - (frequency[a.id] ?? 0);
    });
    // selectedIds is a proxy for "a selection just happened" — frequency
    // lives in a ref (to survive without its own re-render trigger), so this
    // recomputes and re-sorts right after a pick, not just on option changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [options, hasUnassigned, currentUserId, getSelectionFrequency, selectedIds]);

  const handleToggle = useCallback(
    (id: string) => {
      if (!selectedIds.includes(id)) recordSelection(id);
      onToggle(id);
    },
    [selectedIds, recordSelection, onToggle],
  );

  if (entries.length === 0) return null;

  const visible = entries.slice(0, maxAvatars);
  const overflow = entries.slice(maxAvatars);
  const selectedCount = selectedIds.length;

  return (
    <div className="flex items-center gap-2">
      <div className="flex -space-x-2">
        {visible.map((entry) => (
          <AssigneeAvatar
            key={entry.id}
            entry={entry}
            selected={selectedIds.includes(entry.id)}
            onClick={() => handleToggle(entry.id)}
          />
        ))}
        {overflow.length > 0 && (
          <AssigneeOverflowDropdown
            overflow={overflow}
            entries={entries}
            selectedIds={selectedIds}
            onToggle={handleToggle}
            currentUserId={currentUserId}
          />
        )}
      </div>
      {selectedCount > 0 && (
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1 rounded-full bg-cobalt/10 px-2 py-0.5 text-[11px] font-semibold text-cobalt">
            <FilterIcon className="h-3 w-3" />
            Filter {selectedCount}
          </span>
          <button
            type="button"
            onClick={onClear}
            className="text-[11px] font-medium text-muted-foreground hover:text-foreground hover:underline"
          >
            Clear filter
          </button>
        </div>
      )}
    </div>
  );
}
