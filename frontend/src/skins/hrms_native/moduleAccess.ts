/** Module entry points use native effective HRMS grants, never role names. */
export type PermissionModule = 'leave' | 'performance';
type Access = {capabilities: string[]; employee_profile?: boolean};
export function canOpenModule(module: PermissionModule, access?: Access): boolean {
  if (!access) return false;
  if (module === 'leave') {
    return access.employee_profile === true && access.capabilities.some(c => ['leave:create', 'leave:decide'].includes(c));
  }
  return access.capabilities.some(c => ['performance:manage', 'performance:approve_cycle'].includes(c));
}
