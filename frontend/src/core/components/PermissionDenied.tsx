/**
 * PermissionDenied - Shown when user lacks permission to access a resource.
 */

import { ShieldX } from 'lucide-react';

interface PermissionDeniedProps {
  entityType?: string;
  action?: string;
  message?: string;
}

export default function PermissionDenied({
  entityType,
  action,
  message,
}: PermissionDeniedProps) {
  const defaultMessage = entityType && action
    ? `You don't have permission to ${action} ${entityType.split('.').pop()} records.`
    : 'You don\'t have permission to access this resource.';

  return (
    <div className="flex flex-col items-center justify-center py-16 px-4">
      <div className="w-16 h-16 rounded-2xl bg-destructive-subtle flex items-center justify-center mb-4">
        <ShieldX className="w-8 h-8 text-destructive" />
      </div>
      <h3 className="text-lg font-semibold text-foreground mb-2">Access Denied</h3>
      <p className="text-sm text-muted-foreground text-center max-w-sm">
        {message || defaultMessage}
      </p>
      <p className="text-xs text-muted-foreground mt-3">
        Contact your administrator to request access.
      </p>
    </div>
  );
}
