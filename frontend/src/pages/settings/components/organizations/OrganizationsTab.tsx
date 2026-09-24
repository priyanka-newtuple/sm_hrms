/**
 * OrganizationsTab
 *
 * Settings tab for super-admins to manage organizations.
 * Allows viewing pending organization requests, approving/rejecting them,
 * managing existing organizations, and managing users within organizations.
 */

import { useState, useEffect, useCallback } from 'react';
import {
  Loader2,
  AlertCircle,
  RefreshCw,
  Building2,
  Clock,
  Check,
  X,
  Trash2,
  Users,
  Mail,
  ChevronDown,
  ChevronRight,
  Plus,
  UserPlus,
  Shield,
} from 'lucide-react';
import { organizations } from '../../../../core/services/api';
import Badge from '../../../../core/components/Badge';
import { EMAIL_REGEX } from '../../../../core/utils';
import ConfirmDialog from '../../../../core/components/ConfirmDialog';
import { Button } from '@/components/ui/button';

// Status display configuration
const STATUS_CONFIG: Record<string, { label: string; variant: 'success' | 'warning' | 'error' | 'default' | 'cobalt' }> = {
  active: { label: 'Active', variant: 'success' },
  pending: { label: 'Pending', variant: 'warning' },
  suspended: { label: 'Suspended', variant: 'error' },
  rejected: { label: 'Rejected', variant: 'default' },
  archived: { label: 'Archived', variant: 'default' },
};

const ROLE_CONFIG: Record<string, { label: string; variant: 'success' | 'warning' | 'error' | 'default' | 'cobalt' }> = {
  admin: { label: 'Admin', variant: 'cobalt' },
  recruiter: { label: 'Recruiter', variant: 'success' },
  hiring_manager: { label: 'Hiring Manager', variant: 'warning' },
  viewer: { label: 'Viewer', variant: 'default' },
};

interface Organization {
  id: string;
  name: string;
  slug: string;
  domain: string | null;
  status: string;
  requester_email?: string | null;
  requester_name?: string | null;
  created_at: string;
}

interface OrgUser {
  id: string;
  email: string;
  full_name: string;
  avatar_url: string | null;
  role: string;
  status: string;
  auth_type: string;
  is_active: boolean;
  created_at: string;
}

type TabType = 'pending' | 'all';

export default function OrganizationsTab() {
  const [activeTab, setActiveTab] = useState<TabType>('pending');
  const [pendingOrgs, setPendingOrgs] = useState<Organization[]>([]);
  const [allOrgs, setAllOrgs] = useState<Organization[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [deleteConfirmOrg, setDeleteConfirmOrg] = useState<Organization | null>(null);

  // User management state
  const [expandedOrg, setExpandedOrg] = useState<string | null>(null);
  const [orgUsers, setOrgUsers] = useState<Record<string, OrgUser[]>>({});
  const [loadingUsers, setLoadingUsers] = useState<string | null>(null);
  const [deleteConfirmUser, setDeleteConfirmUser] = useState<{ org: Organization; user: OrgUser } | null>(null);
  const [showAddUserForm, setShowAddUserForm] = useState<string | null>(null);
  const [newUserEmail, setNewUserEmail] = useState('');
  const [newUserName, setNewUserName] = useState('');
  const [newUserRole, setNewUserRole] = useState('viewer');
  const [addingUser, setAddingUser] = useState(false);

  const fetchPendingOrgs = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await organizations.listPending();
      setPendingOrgs(data.items as Organization[]);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load pending organizations');
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchAllOrgs = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await organizations.list();
      setAllOrgs(data.items as Organization[]);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load organizations');
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchOrgUsers = useCallback(async (orgId: string) => {
    try {
      setLoadingUsers(orgId);
      const data = await organizations.listUsers(orgId);
      setOrgUsers(prev => ({ ...prev, [orgId]: data.items }));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load users');
    } finally {
      setLoadingUsers(null);
    }
  }, []);

  useEffect(() => {
    if (activeTab === 'pending') {
      fetchPendingOrgs();
    } else {
      fetchAllOrgs();
    }
  }, [activeTab, fetchPendingOrgs, fetchAllOrgs]);

  const handleApprove = async (orgId: string) => {
    try {
      setActionLoading(orgId);
      await organizations.approve(orgId);
      setPendingOrgs(prev => prev.filter(o => o.id !== orgId));
      setAllOrgs(prev => prev.map(o => o.id === orgId ? { ...o, status: 'active' } : o));
      // Refetch if expanded so users list reflects updated statuses immediately
      if (expandedOrg === orgId) {
        await fetchOrgUsers(orgId);
      } else {
        setOrgUsers(prev => { const next = { ...prev }; delete next[orgId]; return next; });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to approve organization');
    } finally {
      setActionLoading(null);
    }
  };

  const handleReject = async (orgId: string) => {
    try {
      setActionLoading(orgId);
      await organizations.reject(orgId);
      setPendingOrgs(prev => prev.filter(o => o.id !== orgId));
      setAllOrgs(prev => prev.map(o => o.id === orgId ? { ...o, status: 'rejected' } : o));
      if (expandedOrg === orgId) {
        await fetchOrgUsers(orgId);
      } else {
        setOrgUsers(prev => { const next = { ...prev }; delete next[orgId]; return next; });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to reject organization');
    } finally {
      setActionLoading(null);
    }
  };

  const handleDelete = async (orgId: string) => {
    try {
      setActionLoading(orgId);
      await organizations.delete(orgId);
      setPendingOrgs(prev => prev.filter(o => o.id !== orgId));
      setAllOrgs(prev => prev.filter(o => o.id !== orgId));
      setDeleteConfirmOrg(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete organization');
    } finally {
      setActionLoading(null);
    }
  };

  const handleToggleExpand = async (orgId: string) => {
    if (expandedOrg === orgId) {
      setExpandedOrg(null);
    } else {
      setExpandedOrg(orgId);
      if (!(orgId in orgUsers)) {
        await fetchOrgUsers(orgId);
      }
    }
    setShowAddUserForm(null);
  };

  const handleAddUser = async (orgId: string) => {
    if (!newUserEmail.trim() || !newUserName.trim()) {
      setError('Please fill in all fields');
      return;
    }
    if (!EMAIL_REGEX.test(newUserEmail.trim())) {
      setError('Please enter a valid email address');
      return;
    }

    try {
      setAddingUser(true);
      await organizations.createUser(orgId, {
        email: newUserEmail,
        full_name: newUserName,
        role: newUserRole,
        status: 'active',
      });
      // Refresh users list
      await fetchOrgUsers(orgId);
      // Reset form
      setNewUserEmail('');
      setNewUserName('');
      setNewUserRole('viewer');
      setShowAddUserForm(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to add user');
    } finally {
      setAddingUser(false);
    }
  };

  const handleDeleteUser = async (orgId: string, userId: string) => {
    try {
      setActionLoading(userId);
      await organizations.deleteUser(orgId, userId);
      // Update local state
      setOrgUsers(prev => ({
        ...prev,
        [orgId]: (prev[orgId] || []).filter(u => u.id !== userId),
      }));
      setDeleteConfirmUser(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete user');
    } finally {
      setActionLoading(null);
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const renderOrgCard = (org: Organization, showApprovalActions: boolean) => (
    <div
      key={org.id}
      className="bg-card rounded-xl border border-border hover:border-border transition-colors"
    >
      <div className="p-6">
        <div className="flex items-start justify-between">
          {/* Org Info */}
          <div className="flex items-start gap-4 flex-1">
            <div className="w-12 h-12 bg-gradient-to-br from-cobalt/20 to-cyan/20 rounded-xl flex items-center justify-center">
              <Building2 className="w-6 h-6 text-cobalt" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <h3 className="text-lg font-semibold text-foreground">{org.name}</h3>
                <Badge variant={STATUS_CONFIG[org.status]?.variant || 'default'}>
                  {STATUS_CONFIG[org.status]?.label || org.status}
                </Badge>
              </div>
              <p className="text-sm text-muted-foreground">/{org.slug}</p>
              {org.domain && (
                <p className="text-sm text-muted-foreground mt-1">Domain: {org.domain}</p>
              )}

              {/* Requester Info */}
              {(org.requester_name || org.requester_email) && (
                <div className="mt-3 flex items-center gap-4 text-sm">
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <Users className="w-4 h-4 text-muted-foreground" />
                    <span>{org.requester_name || 'Unknown'}</span>
                  </div>
                  {org.requester_email && (
                    <div className="flex items-center gap-2 text-muted-foreground">
                      <Mail className="w-4 h-4 text-muted-foreground" />
                      <span>{org.requester_email}</span>
                    </div>
                  )}
                </div>
              )}

              {/* Timestamp */}
              <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
                <Clock className="w-3 h-3" />
                <span>{showApprovalActions ? 'Requested' : 'Created'} {formatDate(org.created_at)}</span>
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2">
            {/* Expand to see users */}
            <Button
              variant="outline"
              onClick={() => handleToggleExpand(org.id)}
              className="flex items-center gap-2 px-3 py-2 hover:text-cobalt hover:bg-muted rounded-lg transition-colors"
              title="View users"
            >
              <Users className="w-4 h-4" />
              {expandedOrg === org.id ? (
                <ChevronDown className="w-4 h-4" />
              ) : (
                <ChevronRight className="w-4 h-4" />
              )}
            </Button>

            {showApprovalActions ? (
              <>
                <Button variant="primary"
                  onClick={() => handleApprove(org.id)}
                  disabled={actionLoading === org.id}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg hover:bg-emerald/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {actionLoading === org.id ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Check className="w-4 h-4" />
                  )}
                  Approve
                </Button>
                <Button
                  variant="outline"
                  onClick={() => handleReject(org.id)}
                  disabled={actionLoading === org.id}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  <X className="w-4 h-4" />
                  Reject
                </Button>
              </>
            ) : null}
            <Button
              variant="outline-danger"
              onClick={() => setDeleteConfirmOrg(org)}
              disabled={actionLoading === org.id}
              className="flex items-center gap-2 px-3 py-2 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              title="Delete organization"
            >
              <Trash2 className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </div>

      {/* Expanded Users Section */}
      {expandedOrg === org.id && (
        <div className=" p-6">
          <div className="flex items-center justify-between mb-4">
            <h4 className="text-sm font-medium text-foreground flex items-center gap-2">
              <Users className="w-4 h-4" />
              Users in {org.name}
            </h4>
            <Button
              variant="outline"
              onClick={() => setShowAddUserForm(showAddUserForm === org.id ? null : org.id)}
              className="flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-cobalt/10 rounded-lg transition-colors"
            >
              <UserPlus className="w-4 h-4" />
              Add User
            </Button>
          </div>

          {/* Add User Form */}
          {showAddUserForm === org.id && (
            <div className="mb-4 p-4 bg-card rounded-lg border border-border">
              <h5 className="text-sm font-medium text-foreground mb-3">Add New User</h5>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <input
                  type="email"
                  placeholder="Email address"
                  value={newUserEmail}
                  onChange={(e) => setNewUserEmail(e.target.value)}
                  className="px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-cobalt focus:border-transparent"
                />
                <input
                  type="text"
                  placeholder="Full name"
                  value={newUserName}
                  onChange={(e) => setNewUserName(e.target.value)}
                  className="px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-cobalt focus:border-transparent"
                />
                <select
                  value={newUserRole}
                  onChange={(e) => setNewUserRole(e.target.value)}
                  className="px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-cobalt focus:border-transparent"
                >
                  <option value="viewer">Viewer</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
              <div className="flex justify-end gap-2 mt-3">
                <Button variant="primary"
                  onClick={() => setShowAddUserForm(null)}
                  className="px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted rounded-lg transition-colors"
                >
                  Cancel
                </Button>
                <Button variant="primary"
                  onClick={() => handleAddUser(org.id)}
                  disabled={addingUser}
                  className="flex items-center gap-2 px-3 py-1.5 text-sm bg-cobalt text-white rounded-lg hover:bg-cobalt/90 disabled:opacity-50 transition-colors"
                >
                  {addingUser ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Plus className="w-4 h-4" />
                  )}
                  Add User
                </Button>
              </div>
              <p className="text-xs text-muted-foreground mt-2">
                User will be created with a temporary password. They should use password reset or Google OAuth to set up their account.
              </p>
            </div>
          )}

          {/* Users List */}
          {loadingUsers === org.id ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-6 h-6 text-cobalt animate-spin" />
            </div>
          ) : (orgUsers[org.id] || []).length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <Users className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p>No users in this organization</p>
            </div>
          ) : (
            <div className="space-y-2">
              {(orgUsers[org.id] || []).map((user) => (
                <div
                  key={user.id}
                  className="flex items-center justify-between p-3 bg-card rounded-lg border border-border"
                >
                  <div className="flex items-center gap-3">
                    {user.avatar_url ? (
                      <img
                        src={user.avatar_url}
                        alt={user.full_name}
                        className="w-8 h-8 rounded-full"
                      />
                    ) : (
                      <div className="w-8 h-8 bg-accent rounded-full flex items-center justify-center">
                        <span className="text-sm font-medium text-muted-foreground">
                          {user.full_name.charAt(0).toUpperCase()}
                        </span>
                      </div>
                    )}
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-foreground">{user.full_name}</span>
                        <Badge variant={ROLE_CONFIG[user.role]?.variant || 'default'} size="sm">
                          {ROLE_CONFIG[user.role]?.label || user.role}
                        </Badge>
                        <Badge variant={STATUS_CONFIG[user.status]?.variant || 'default'} size="sm">
                          {STATUS_CONFIG[user.status]?.label || user.status}
                        </Badge>
                      </div>
                      <span className="text-sm text-muted-foreground">{user.email}</span>
                    </div>
                  </div>
                  <Button
                    variant="outline-danger"
                    onClick={() => setDeleteConfirmUser({ org, user })}
                    disabled={actionLoading === user.id}
                    className="p-2 "
                    title="Delete user"
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );

  if (loading && pendingOrgs.length === 0 && allOrgs.length === 0) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-8 h-8 text-cobalt animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header with Tabs */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Shield className="w-5 h-5 text-muted-foreground" />
            <h2 className="text-lg font-medium text-foreground">Organization Management</h2>
          </div>

          {/* Tabs */}
          <div className="flex bg-muted rounded-lg p-1">
            <Button variant="primary"
              onClick={() => setActiveTab('pending')}
              className={`px-4 py-1.5 text-sm font-medium rounded-md transition-colors ${
                activeTab === 'pending'
                  ? 'bg-card text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              Pending
              {pendingOrgs.length > 0 && (
                <span className="ml-2 px-1.5 py-0.5 bg-warning-subtle text-warning text-xs rounded-full">
                  {pendingOrgs.length}
                </span>
              )}
            </Button>
            <Button variant="primary"
              onClick={() => setActiveTab('all')}
              className={`px-4 py-1.5 text-sm font-medium rounded-md transition-colors ${
                activeTab === 'all'
                  ? 'bg-card text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              All Organizations
            </Button>
          </div>
        </div>

        <Button variant="primary"
          onClick={() => activeTab === 'pending' ? fetchPendingOrgs() : fetchAllOrgs()}
          className="flex items-center gap-2 px-3 py-2 text-muted-foreground hover:text-cobalt hover:bg-muted rounded-lg transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </Button>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 p-4 bg-destructive-subtle border border-destructive/30 rounded-xl text-destructive">
          <AlertCircle className="w-5 h-5 flex-shrink-0" />
          <p>{error}</p>
          <Button variant="primary"
            onClick={() => setError(null)}
            className="ml-auto text-destructive hover:text-destructive"
          >
            <X className="w-4 h-4" />
          </Button>
        </div>
      )}

      {/* Content based on active tab */}
      {activeTab === 'pending' ? (
        /* Pending Organizations */
        pendingOrgs.length === 0 ? (
          <div className="bg-card rounded-xl border border-border p-12 text-center">
            <div className="w-16 h-16 bg-muted rounded-full flex items-center justify-center mx-auto mb-4">
              <Building2 className="w-8 h-8 text-muted-foreground" />
            </div>
            <h3 className="text-lg font-medium text-foreground mb-2">No pending requests</h3>
            <p className="text-muted-foreground">
              Organization requests will appear here when users request to create new organizations.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {pendingOrgs.map((org) => renderOrgCard(org, true))}
          </div>
        )
      ) : (
        /* All Organizations */
        allOrgs.length === 0 ? (
          <div className="bg-card rounded-xl border border-border p-12 text-center">
            <div className="w-16 h-16 bg-muted rounded-full flex items-center justify-center mx-auto mb-4">
              <Building2 className="w-8 h-8 text-muted-foreground" />
            </div>
            <h3 className="text-lg font-medium text-foreground mb-2">No organizations</h3>
            <p className="text-muted-foreground">
              Organizations will appear here once created.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {allOrgs.map((org) => renderOrgCard(org, org.status === 'pending'))}
          </div>
        )
      )}

      {/* Delete Organization Confirmation Dialog */}
      <ConfirmDialog
        open={!!deleteConfirmOrg}
        title="Delete Organization?"
        message={`Are you sure you want to delete "${deleteConfirmOrg?.name}"? This will also delete all associated data and cannot be undone.`}
        confirmLabel="Delete"
        variant="danger"
        onConfirm={() => deleteConfirmOrg && handleDelete(deleteConfirmOrg.id)}
        onClose={() => setDeleteConfirmOrg(null)}
      />

      {/* Delete User Confirmation Dialog */}
      <ConfirmDialog
        open={!!deleteConfirmUser}
        title="Delete User?"
        message={`Are you sure you want to delete "${deleteConfirmUser?.user.full_name}" (${deleteConfirmUser?.user.email}) from ${deleteConfirmUser?.org.name}? This action cannot be undone.`}
        confirmLabel="Delete"
        variant="danger"
        onConfirm={() => deleteConfirmUser && handleDeleteUser(deleteConfirmUser.org.id, deleteConfirmUser.user.id)}
        onClose={() => setDeleteConfirmUser(null)}
      />
    </div>
  );
}
