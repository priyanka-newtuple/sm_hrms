/**
 * RoleList
 *
 * Presentational list of roles. Renders an empty state when there are none.
 */

import { Shield } from 'lucide-react';
import EmptyState from '../../../../core/components/EmptyState';
import type { RoleListItem } from '../../../../core/types';
import RoleListRow from './RoleListRow';

interface RoleListProps {
  roles: RoleListItem[];
  /** Id of the role currently running a duplicate/delete action, if any. */
  actionLoadingId: string | null;
  onEdit: (roleId: string) => void;
  onDuplicate: (role: RoleListItem) => void;
  onDelete: (role: RoleListItem) => void;
}

export default function RoleList({ roles, actionLoadingId, onEdit, onDuplicate, onDelete }: RoleListProps) {
  if (roles.length === 0) {
    return (
      <EmptyState
        surface="panel"
        icon={<Shield className="h-12 w-12 text-muted-foreground/60" />}
        title="No roles configured"
        description="Create roles to manage user permissions."
      />
    );
  }

  return (
    <div className="space-y-3">
      {roles.map((role) => (
        <RoleListRow
          key={role.id}
          role={role}
          actionLoading={actionLoadingId === role.id}
          onEdit={onEdit}
          onDuplicate={onDuplicate}
          onDelete={onDelete}
        />
      ))}
    </div>
  );
}
