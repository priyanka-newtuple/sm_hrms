import type { ColumnDef } from '@tanstack/react-table';
import { Check, ChevronDown, Loader2, UserCheck, UserMinus } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from '@/components/ui/dropdown-menu';
import { DataTable, DateCell, actionsColumn } from '@/core/components/DataTable';
import Badge from '../../../../core/components/Badge';
import type { RoleListItem, User, UserRole, UserStatus } from '../../../../core/types';

/** Legacy role labels (fallback when no RBAC roles exist). */
const ROLE_LABELS: Record<UserRole, string> = {
  superadmin: 'Super Admin',
  admin: 'Admin',
  recruiter: 'Recruiter',
  hiring_manager: 'Hiring Manager',
  viewer: 'Viewer',
};

/** Role accent, carried by a small dot rather than a filled pill. */
const ROLE_DOT: Record<string, string> = {
  superadmin: 'bg-rose-500',
  admin: 'bg-purple-500',
  recruiter: 'bg-sky-500',
  hiring_manager: 'bg-emerald-500',
  viewer: 'bg-muted-foreground/40',
};

const DEFAULT_ROLE_DOT = 'bg-muted-foreground/40';

const STATUS_CONFIG: Record<
  UserStatus,
  { label: string; variant: 'success' | 'warning' | 'error' | 'default' }
> = {
  active: { label: 'Active', variant: 'success' },
  pending: { label: 'Pending', variant: 'warning' },
  suspended: { label: 'Suspended', variant: 'error' },
  rejected: { label: 'Rejected', variant: 'default' },
};

function getRoleDisplay(
  roleName: string,
  rbacRoles: RoleListItem[],
): { label: string; dot: string } {
  const rbacMatch = rbacRoles.find((role) => role.name === roleName);
  const dot = ROLE_DOT[roleName] ?? DEFAULT_ROLE_DOT;
  if (rbacMatch) return { label: rbacMatch.display_name, dot };
  return { label: ROLE_LABELS[roleName as UserRole] ?? roleName, dot };
}

type Props = {
  users: User[];
  rbacRoles: RoleListItem[];
  canWrite: boolean;
  /** Id of the user whose action is in flight. */
  actionLoading: string | null;
  onRoleChange: (userId: string, newRole: UserRole, rbacRole?: RoleListItem) => void;
  onSuspend: (userId: string) => void;
  onReactivate: (userId: string) => void;
};

export default function UsersTable({
  users,
  rbacRoles,
  canWrite,
  actionLoading,
  onRoleChange,
  onSuspend,
  onReactivate,
}: Props) {
  const columns: ColumnDef<User, unknown>[] = [
    {
      id: 'user',
      header: 'User',
      accessorFn: (user) => user.full_name,
      cell: ({ row }) => (
        <div className="flex items-center gap-3">
          {row.original.avatar_url ? (
            <img
              src={row.original.avatar_url}
              alt={row.original.full_name}
              className="size-8 rounded-full object-cover"
            />
          ) : (
            <div className="flex size-8 items-center justify-center rounded-full bg-accent">
              <span className="text-sm font-medium text-muted-foreground">
                {row.original.full_name.charAt(0).toUpperCase()}
              </span>
            </div>
          )}
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-foreground">{row.original.full_name}</p>
            <p className="truncate text-xs text-muted-foreground">{row.original.email}</p>
          </div>
        </div>
      ),
    },
    {
      id: 'status',
      header: 'Status',
      accessorFn: (user) => user.status,
      cell: ({ row }) => (
        <Badge variant={STATUS_CONFIG[row.original.status].variant}>
          {STATUS_CONFIG[row.original.status].label}
        </Badge>
      ),
      meta: { width: '8rem' },
    },
    {
      id: 'role',
      header: 'Role',
      enableSorting: false,
      cell: ({ row }) => {
        const display = getRoleDisplay(row.original.role, rbacRoles);
        return (
          <DropdownMenu>
            <DropdownMenuTrigger
              disabled={!canWrite}
              className={cn(
                'flex h-7 max-w-full items-center gap-2 rounded-md px-2 text-sm text-foreground transition-colors',
                canWrite
                  ? 'cursor-pointer hover:bg-muted'
                  : 'cursor-default px-0 text-muted-foreground',
              )}
            >
              <span className={cn('size-1.5 shrink-0 rounded-full', display.dot)} />
              <span className="truncate whitespace-nowrap">{display.label}</span>
              {canWrite && (
                <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" />
              )}
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              {rbacRoles.length > 0
                ? [...rbacRoles]
                    .sort((a, b) => b.priority - a.priority)
                    .map((role) => {
                      const legacyRole = role.name as UserRole;
                      return (
                        <DropdownMenuItem
                          key={role.id}
                          onClick={() => onRoleChange(row.original.id, legacyRole, role)}
                          disabled={!canWrite}
                        >
                          <span
                            className={cn(
                              'size-1.5 shrink-0 rounded-full',
                              ROLE_DOT[role.name] ?? DEFAULT_ROLE_DOT,
                            )}
                          />
                          {role.display_name}
                          {row.original.role === legacyRole && (
                            <Check className="ml-auto size-3 text-success" />
                          )}
                        </DropdownMenuItem>
                      );
                    })
                : (Object.keys(ROLE_LABELS) as UserRole[]).map((role) => (
                    <DropdownMenuItem
                      key={role}
                      onClick={() => onRoleChange(row.original.id, role)}
                      disabled={!canWrite}
                    >
                      <span
                        className={cn(
                          'size-1.5 shrink-0 rounded-full',
                          ROLE_DOT[role] ?? DEFAULT_ROLE_DOT,
                        )}
                      />
                      {ROLE_LABELS[role]}
                      {row.original.role === role && (
                        <Check className="ml-auto size-3 text-success" />
                      )}
                    </DropdownMenuItem>
                  ))}
            </DropdownMenuContent>
          </DropdownMenu>
        );
      },
      meta: { width: '14rem' },
    },
    {
      id: 'last_login',
      header: 'Last login',
      accessorFn: (user) => user.last_login_at ?? '',
      cell: ({ row }) => (
        <DateCell>
          {row.original.last_login_at
            ? new Date(row.original.last_login_at).toLocaleDateString()
            : 'Never'}
        </DateCell>
      ),
      meta: { width: '10rem' },
    },
    actionsColumn<User>({
      alwaysVisible: true,
      render: (user) => (
        <>
          {user.status === 'active' && (
            <Button
              variant="ghost-danger"
              size="icon"
              onClick={() => onSuspend(user.id)}
              disabled={!canWrite || actionLoading === user.id}
              title="Suspend user"
            >
              {actionLoading === user.id ? <Loader2 className="animate-spin" /> : <UserMinus />}
            </Button>
          )}
          {user.status === 'suspended' && (
            <Button
              variant="ghost-action"
              size="icon"
              onClick={() => onReactivate(user.id)}
              disabled={!canWrite || actionLoading === user.id}
              title="Reactivate user"
            >
              {actionLoading === user.id ? <Loader2 className="animate-spin" /> : <UserCheck />}
            </Button>
          )}
        </>
      ),
    }),
  ];

  return (
    <DataTable
      label="Organization users"
      data={users}
      columns={columns}
      getRowId={(user) => user.id}
      // The surrounding Panel already draws the frame.
      framed={false}
      emptyState={{ title: 'No users found' }}
    />
  );
}
