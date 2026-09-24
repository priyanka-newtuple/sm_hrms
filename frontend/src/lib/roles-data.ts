export const MAX_PRIORITY = 100

export interface Role {
  id: string
  name: string
  display_name: string
  description: string | null
  is_system: boolean
  priority: number
  color: string
  user_count: number
}

export const COLOR_PALETTE = [
  '#4F46E5', '#7C3AED', '#DB2777', '#DC2626', '#EA580C',
  '#D97706', '#16A34A', '#0891B2', '#0284C7', '#2563EB',
]

/**
 * Converts a hex color string to an `rgba(...)` CSS value.
 *
 * @param hex - 6-digit hex color (with or without leading `#`).
 * @param alpha - Opacity, 0–1.
 * @returns CSS `rgba(r, g, b, alpha)` string.
 */
export function hexToRgba(hex: string, alpha: number): string {
  const clean = hex.replace('#', '')
  const r = parseInt(clean.substring(0, 2), 16)
  const g = parseInt(clean.substring(2, 4), 16)
  const b = parseInt(clean.substring(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

export const ROLES_DATA: Role[] = [
  {
    id: 'superadmin',
    name: 'superadmin',
    display_name: 'Super Admin',
    description: 'Full platform access across all organizations',
    is_system: true,
    priority: 100,
    color: '#7C3AED',
    user_count: 1,
  },
  {
    id: 'admin',
    name: 'admin',
    display_name: 'Admin',
    description: 'Full access to all resources in the organization',
    is_system: true,
    priority: 90,
    color: '#4F46E5',
    user_count: 2,
  },
  {
    id: 'recruiter',
    name: 'recruiter',
    display_name: 'Recruiter',
    description: 'Manage candidates, jobs, and applications',
    is_system: true,
    priority: 60,
    color: '#0284C7',
    user_count: 8,
  },
  {
    id: 'hiring_manager',
    name: 'hiring_manager',
    display_name: 'Hiring Manager',
    description: 'Review and approve candidates for their teams',
    is_system: true,
    priority: 50,
    color: '#16A34A',
    user_count: 14,
  },
  {
    id: 'viewer',
    name: 'viewer',
    display_name: 'Viewer',
    description: 'Read-only access to candidates and jobs',
    is_system: false,
    priority: 10,
    color: '#71717A',
    user_count: 5,
  },
]

export function getRoleById(id: string): Role | undefined {
  return ROLES_DATA.find((r) => r.id === id)
}
