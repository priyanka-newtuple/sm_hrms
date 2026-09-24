/** Palette used by `getAvatarColorClass` to assign a deterministic color per
 *  user id. Kept in its own file (rather than inline in the utils barrel)
 *  since it's data, not logic — lives in `core/utils` rather than a
 *  feature-specific folder because `getAvatarColorClass` itself is shared
 *  well beyond Pipeline (e.g. `core/components/AvatarStack.tsx`). */
export const AVATAR_COLORS = [
  'bg-cobalt',
  'bg-cyan',
  'bg-violet',
  'bg-rose',
  'bg-amber-500',
  'bg-emerald-500',
  'bg-sky-500',
  'bg-purple-500',
];
