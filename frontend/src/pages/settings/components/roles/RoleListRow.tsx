/**
 * RoleListRow
 *
 * A single role row: identity, metadata, and edit/duplicate/delete actions.
 */

import { Shield, Copy, Pencil, Trash2, Users } from 'lucide-react';
import { Button } from '@/components/ui/button';
import Badge from '../../../../core/components/Badge';
import Panel from '../../../../core/components/Panel';
import type { RoleListItem } from '../../../../core/types';
import { getRoleColor } from './roleColors';

interface RoleListRowProps {
  role: RoleListItem;
  actionLoading: boolean;
  onEdit: (roleId: string) => void;
  onDuplicate: (role: RoleListItem) => void;
  onDelete: (role: RoleListItem) => void;
}

export default function RoleListRow({ role, actionLoading, onEdit, onDuplicate, onDelete }: RoleListRowProps) {
  return (
    <Panel className="transition-colors hover:border-border">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${getRoleColor(role)}`}>
            <Shield className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-medium text-foreground">{role.display_name}</span>
              {role.is_system && <Badge variant="default">System</Badge>}
              <span className="text-xs text-muted-foreground">Priority: {role.priority}</span>
            </div>
            {role.description && <p className="mt-0.5 text-sm text-muted-foreground">{role.description}</p>}
            <div className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
              <Users className="h-3 w-3" />
              {role.user_count} {role.user_count === 1 ? 'user' : 'users'}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1">
          <Button variant="ghost-action" size="icon" onClick={() => onEdit(role.id)} title="Edit role">
            <Pencil className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost-action"
            size="icon"
            onClick={() => onDuplicate(role)}
            disabled={actionLoading}
            loading={actionLoading}
            title="Duplicate role"
          >
            <Copy className="h-4 w-4" />
          </Button>
          {!role.is_system && (
            <Button
              variant="ghost-danger"
              size="icon"
              onClick={() => onDelete(role)}
              disabled={actionLoading}
              loading={actionLoading}
              title="Delete role"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>
    </Panel>
  );
}
