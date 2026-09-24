/**
 * PermissionGate - Conditionally renders children based on RBAC permissions.
 *
 * Usage:
 *   <PermissionGate entityType="ATS.Candidate" action="edit">
 *     <EditButton />
 *   </PermissionGate>
 */

import type { ReactNode } from 'react';
import { usePermissions } from '../hooks/usePermissions';
import type { PermissionAction } from '../types';

interface PermissionGateProps {
  entityType: string;
  action: PermissionAction;
  children: ReactNode;
  fallback?: ReactNode;
}

export default function PermissionGate({
  entityType,
  action,
  children,
  fallback = null,
}: PermissionGateProps) {
  const { can, loading } = usePermissions();

  // Don't block during loading
  if (loading) return <>{children}</>;

  if (!can(action, entityType)) {
    return <>{fallback}</>;
  }

  return <>{children}</>;
}
