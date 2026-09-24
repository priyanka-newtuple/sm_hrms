/** A distinct assignee (or the "Unassigned" bucket) shown in the filter row. */
export interface AssigneeEntry {
  id: string;
  name: string;
}

/** Overlapping circle, sized/bordered/shadowed to read as a solid, tactile
 *  chip — shared by AssigneeAvatarFilter's avatar row and
 *  AssigneeOverflowDropdown's "+N" trigger so both read as one consistent
 *  set of chips. Lives in its own leaf module (rather than being exported
 *  from either component) so the two don't import from each other. */
export const AVATAR_BASE =
  'inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2 border-white text-xs font-semibold text-white shadow-sm transition hover:z-10 hover:scale-110';
