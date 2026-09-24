/**
 * UsersTab
 *
 * Settings tab for managing organization users.
 * Allows admins to view, approve/reject, suspend, and manage user roles.
 */

import { useState, useEffect, useCallback } from 'react';
import {
  Loader2,
  RefreshCw,
  Users,
  Clock,
  Check,
  X,
  UserPlus,
  Mail,
  RotateCcw,
  Trash2,
} from 'lucide-react';
import { users, roles as rolesApi, invitations } from '../../../../core/services/api';
import { usePermissions } from '../../../../core/hooks/usePermissions';
import { useRoles } from '../../../../core/hooks/useRoles';
import type { User, UserRole, RoleListItem, Invitation } from '../../../../core/types';
import AlertBanner from '../../../../core/components/AlertBanner';
import PermissionDenied from '../../../../core/components/PermissionDenied';
import { Button } from '@/components/ui/button';
import Panel from '../../../../core/components/Panel';
import SectionHeader from '../../../../core/components/SectionHeader';
import InviteUserDialog from './InviteUserDialog';
import UsersTable from './UsersTable';

export default function UsersTab() {
  const [allUsers, setAllUsers] = useState<User[]>([]);
  const [pendingInvitations, setPendingInvitations] = useState<Invitation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [inviteDialogOpen, setInviteDialogOpen] = useState(false);
  const { roles: rbacRoles } = useRoles();
  const { hasPermission } = usePermissions();
  const canWrite = hasPermission('user:write');

  const fetchUsers = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [usersData, invitationsData] = await Promise.all([
        users.list(),
        invitations.list('pending'),
      ]);
      setAllUsers(usersData);
      setPendingInvitations(invitationsData);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load users');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const handleApprove = async (userId: string) => {
    if (!canWrite) return;
    try {
      setActionLoading(userId);
      const updatedUser = await users.approve(userId);
      setAllUsers(prev => prev.map(u => u.id === userId ? updatedUser : u));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to approve user');
    } finally {
      setActionLoading(null);
    }
  };

  const handleReject = async (userId: string) => {
    if (!canWrite) return;
    try {
      setActionLoading(userId);
      const updatedUser = await users.reject(userId);
      setAllUsers(prev => prev.map(u => u.id === userId ? updatedUser : u));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to reject user');
    } finally {
      setActionLoading(null);
    }
  };

  const handleSuspend = async (userId: string) => {
    if (!canWrite) return;
    try {
      setActionLoading(userId);
      const updatedUser = await users.suspend(userId);
      setAllUsers(prev => prev.map(u => u.id === userId ? updatedUser : u));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to suspend user');
    } finally {
      setActionLoading(null);
    }
  };

  const handleReactivate = async (userId: string) => {
    if (!canWrite) return;
    try {
      setActionLoading(userId);
      const updatedUser = await users.reactivate(userId);
      setAllUsers(prev => prev.map(u => u.id === userId ? updatedUser : u));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to reactivate user');
    } finally {
      setActionLoading(null);
    }
  };

  const handleRoleChange = async (userId: string, newRole: UserRole, rbacRole?: RoleListItem) => {
    if (!canWrite) return;
    try {
      setActionLoading(userId);
      // Update legacy role
      const updatedUser = await users.updateRole(userId, newRole);
      // Also set RBAC role if available
      if (rbacRole) {
        try {
          await rolesApi.setUserRole(userId, { role_id: rbacRole.id });
        } catch {
          // RBAC role assignment is best-effort; legacy role is primary
        }
      }
      setAllUsers(prev => prev.map(u => u.id === userId ? updatedUser : u));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update role');
    } finally {
      setActionLoading(null);
    }
  };

  const handleResendInvitation = async (invitationId: string) => {
    if (!canWrite) return;
    try {
      setActionLoading(invitationId);
      await invitations.resend(invitationId);
      fetchUsers(); // Refresh list
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to resend invitation');
    } finally {
      setActionLoading(null);
    }
  };

  const handleRevokeInvitation = async (invitationId: string) => {
    if (!canWrite) return;
    try {
      setActionLoading(invitationId);
      await invitations.revoke(invitationId);
      setPendingInvitations(prev => prev.filter(inv => inv.id !== invitationId));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to revoke invitation');
    } finally {
      setActionLoading(null);
    }
  };

  // Separate pending users
  const pendingUsers = allUsers.filter(u => u.status === 'pending');
  const otherUsers = allUsers.filter(u => u.status !== 'pending');

  // Stats
  const stats = {
    total: allUsers.length,
    active: allUsers.filter(u => u.status === 'active').length,
    pending: pendingUsers.length,
    suspended: allUsers.filter(u => u.status === 'suspended').length,
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-8 h-8 text-cobalt animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <SectionHeader
        title="User Management"
        description={`${stats.total} users · ${stats.active} active · ${stats.pending} pending`}
        icon={<Users className="w-5 h-5" />}
        actions={(
          <>
            <Button variant="ghost" onClick={fetchUsers} icon={<RefreshCw className="w-4 h-4" />}>
              Refresh
            </Button>
            <Button
              variant="primary"
              onClick={() => setInviteDialogOpen(true)}
              icon={<UserPlus className="w-4 h-4" />}
              disabled={!canWrite}
            >
              Invite User
            </Button>
          </>
        )}
      />

      {!canWrite && (
        <PermissionDenied message="You have read-only access to Users. Contact an admin to manage invites, approvals, roles, or account status." />
      )}

      {error && (
        <AlertBanner tone="error" title="Error">
          {error}
        </AlertBanner>
      )}

      {/* Pending approvals section */}
      {pendingUsers.length > 0 && (
        <div className="bg-warning-subtle border border-warning/30 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-4">
            <Clock className="w-5 h-5 text-warning" />
            <h3 className="font-medium text-warning">
              Pending Approvals ({pendingUsers.length})
            </h3>
          </div>
          <div className="space-y-3">
            {pendingUsers.map(user => (
              <div
                key={user.id}
                className="bg-card rounded-lg border border-warning/30 p-4 flex items-center justify-between"
              >
                <div className="flex items-center gap-3">
                  {user.avatar_url ? (
                    <img
                      src={user.avatar_url}
                      alt={user.full_name}
                      className="w-10 h-10 rounded-full"
                    />
                  ) : (
                    <div className="w-10 h-10 bg-accent rounded-full flex items-center justify-center">
                      <span className="text-muted-foreground font-medium">
                        {user.full_name.charAt(0).toUpperCase()}
                      </span>
                    </div>
                  )}
                  <div>
                    <p className="font-medium text-foreground">{user.full_name}</p>
                    <p className="text-sm text-muted-foreground">{user.email}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="success"
                    size="sm"
                    onClick={() => handleApprove(user.id)}
                    disabled={!canWrite || actionLoading === user.id}
                    loading={actionLoading === user.id}
                    icon={<Check className="w-4 h-4" />}
                  >
                    Approve
                  </Button>
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => handleReject(user.id)}
                    disabled={!canWrite || actionLoading === user.id}
                    loading={actionLoading === user.id}
                    icon={<X className="w-4 h-4" />}
                  >
                    Reject
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Pending invitations section */}
      {pendingInvitations.length > 0 && (
        <div className="bg-info-subtle border border-info/30 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-4">
            <Mail className="w-5 h-5 text-info" />
            <h3 className="font-medium text-info">
              Pending Invitations ({pendingInvitations.length})
            </h3>
          </div>
          <div className="space-y-3">
            {pendingInvitations.map(invitation => (
              <div
                key={invitation.id}
                className="bg-card rounded-lg border border-info/30 p-4 flex items-center justify-between"
              >
                <div>
                  <p className="font-medium text-foreground">{invitation.email}</p>
                  <p className="text-sm text-muted-foreground">
                    Role: {invitation.role.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())} ·
                    Expires: {new Date(invitation.expires_at).toLocaleDateString()}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline-info"
                    size="sm"
                    onClick={() => handleResendInvitation(invitation.id)}
                    disabled={!canWrite || actionLoading === invitation.id}
                    loading={actionLoading === invitation.id}
                    icon={<RotateCcw className="w-4 h-4" />}
                    title="Resend invitation"
                  >
                    Resend
                  </Button>
                  <Button
                    variant="outline-danger"
                    size="sm"
                    onClick={() => handleRevokeInvitation(invitation.id)}
                    disabled={!canWrite || actionLoading === invitation.id}
                    loading={actionLoading === invitation.id}
                    icon={<Trash2 className="w-4 h-4" />}
                    title="Revoke invitation"
                  >
                    Revoke
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <Panel padding="none" overflowHidden>
        <UsersTable
          users={otherUsers}
          rbacRoles={rbacRoles}
          canWrite={canWrite}
          actionLoading={actionLoading}
          onRoleChange={handleRoleChange}
          onSuspend={handleSuspend}
          onReactivate={handleReactivate}
        />
      </Panel>

      {/* Invite User Dialog */}
      <InviteUserDialog
        open={inviteDialogOpen}
        onClose={() => setInviteDialogOpen(false)}
        onInvited={fetchUsers}
        canWrite={canWrite}
      />
    </div>
  );
}
