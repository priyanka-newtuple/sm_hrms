/**
 * Role color resolution.
 *
 * Tailwind only ships classes it can see as complete literal strings, so a
 * role's color MUST map to a static class string here — never interpolate
 * `bg-${color}-100`, which gets purged from the build and renders nothing.
 */

import type { RoleListItem } from '../../../../core/types';

const FALLBACK = 'bg-gray-100 text-gray-700';

// Safelist keyed by the color token stored on a role (role.color).
const COLOR_CLASS_MAP: Record<string, string> = {
  gray: 'bg-gray-100 text-gray-700',
  red: 'bg-red-100 text-red-700',
  orange: 'bg-orange-100 text-orange-700',
  amber: 'bg-amber-100 text-amber-700',
  yellow: 'bg-yellow-100 text-yellow-700',
  green: 'bg-green-100 text-green-700',
  emerald: 'bg-emerald-100 text-emerald-700',
  teal: 'bg-teal-100 text-teal-700',
  cyan: 'bg-cyan-100 text-cyan-700',
  blue: 'bg-blue-100 text-blue-700',
  indigo: 'bg-indigo-100 text-indigo-700',
  violet: 'bg-violet-100 text-violet-700',
  purple: 'bg-purple-100 text-purple-700',
  pink: 'bg-pink-100 text-pink-700',
};

// Fallback mapping by well-known role name when no color is set.
const ROLE_NAME_CLASS_MAP: Record<string, string> = {
  admin: 'bg-purple-100 text-purple-700',
  recruiter: 'bg-blue-100 text-blue-700',
  hiring_manager: 'bg-green-100 text-green-700',
  viewer: 'bg-gray-100 text-gray-700',
};

export function getRoleColor(role: Pick<RoleListItem, 'name' | 'color'>): string {
  if (role.color && COLOR_CLASS_MAP[role.color]) {
    return COLOR_CLASS_MAP[role.color];
  }
  return ROLE_NAME_CLASS_MAP[role.name] || FALLBACK;
}
