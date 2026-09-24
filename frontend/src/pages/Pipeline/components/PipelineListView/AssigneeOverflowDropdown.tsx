import { User as UserIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import { getInitials, getAvatarColorClass } from '@/core/utils';
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuLabel,
  DropdownMenuCheckboxItem,
} from '@/components/ui/dropdown-menu';
import { UNASSIGNED_FILTER } from '../../hooks/useAssigneeFilter';
import { AVATAR_BASE, type AssigneeEntry } from './assigneeAvatarStyles';

interface AssigneeOverflowDropdownProps {
  /** Entries not shown directly in the avatar row (beyond `maxAvatars`). */
  overflow: AssigneeEntry[];
  /** Full entry list, shown in the checkbox picker regardless of overflow. */
  entries: AssigneeEntry[];
  selectedIds: string[];
  onToggle: (id: string) => void;
  currentUserId?: string;
}

/** "+N" avatar-styled trigger that opens a full checkbox picker for every
 *  assignee — the overflow half of AssigneeAvatarFilter's avatar row. */
export default function AssigneeOverflowDropdown({
  overflow,
  entries,
  selectedIds,
  onToggle,
  currentUserId,
}: AssigneeOverflowDropdownProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        title={overflow.map((e) => e.name).join(', ')}
        aria-label={`Filter by ${overflow.length} more assignees`}
        className={cn(
          AVATAR_BASE,
          'bg-muted-foreground hover:bg-muted-foreground/80',
          overflow.some((e) => selectedIds.includes(e.id)) && 'ring-2 ring-cobalt ring-offset-1',
        )}
      >
        +{overflow.length}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" sideOffset={8} className="w-56 p-1.5">
        <DropdownMenuGroup>
          <DropdownMenuLabel className="px-2 pt-1 pb-1 text-[11px] font-semibold uppercase tracking-wider">
            Filter by assignee
          </DropdownMenuLabel>
          {entries.map((entry) => (
            <DropdownMenuCheckboxItem
              key={entry.id}
              checked={selectedIds.includes(entry.id)}
              onCheckedChange={() => onToggle(entry.id)}
              className="gap-2"
            >
              <span
                className={cn(
                  'inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[9px] font-semibold text-white',
                  entry.id === UNASSIGNED_FILTER ? 'bg-muted-foreground' : getAvatarColorClass(entry.id),
                )}
              >
                {entry.id === UNASSIGNED_FILTER ? <UserIcon className="h-2.5 w-2.5" /> : getInitials(entry.name)}
              </span>
              {entry.id === currentUserId ? `${entry.name} (me)` : entry.name}
            </DropdownMenuCheckboxItem>
          ))}
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
