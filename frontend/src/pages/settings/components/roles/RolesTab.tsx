/**
 * RolesTab
 *
 * Settings tab for managing RBAC roles.
 * Allows admins to view, create, edit, duplicate, and delete roles.
 */

import { useState, useMemo } from 'react';
import { Loader2, RefreshCw, Shield, Plus } from 'lucide-react';
import { useRoles } from '../../../../core/hooks/useRoles';
import type { RoleListItem } from '../../../../core/types';
import AlertBanner from '../../../../core/components/AlertBanner';
import { Button } from '@/components/ui/button';
import ConfirmDialog from '../../../../core/components/ConfirmDialog';
import SectionHeader from '../../../../core/components/SectionHeader';
import RoleList from './RoleList';
import RoleEditor from './RoleEditor';

export default function RolesTab() {
  const { roles, loading, error, refetch, deleteRole, duplicateRole } = useRoles();
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingRoleId, setEditingRoleId] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<RoleListItem | null>(null);

  // Sort roles by priority (highest first).
  const sortedRoles = useMemo(
    () => [...roles].sort((a, b) => b.priority - a.priority),
    [roles],
  );

  const handleCreate = () => {
    setEditingRoleId(null);
    setEditorOpen(true);
  };

  const handleEdit = (roleId: string) => {
    setEditingRoleId(roleId);
    setEditorOpen(true);
  };

  const handleDuplicate = async (role: RoleListItem) => {
    try {
      setActionLoading(role.id);
      setActionError(null);
      await duplicateRole(role.id, {
        name: `${role.name}_copy`,
        display_name: `${role.display_name} (Copy)`,
      });
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Failed to duplicate role');
    } finally {
      setActionLoading(null);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    const role = deleteTarget;
    try {
      setActionLoading(role.id);
      setActionError(null);
      await deleteRole(role.id);
      setDeleteTarget(null);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Failed to delete role');
    } finally {
      setActionLoading(null);
    }
  };

  const handleEditorClose = () => {
    setEditorOpen(false);
    setEditingRoleId(null);
  };

  const handleEditorSave = () => {
    setEditorOpen(false);
    setEditingRoleId(null);
    void refetch();
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-cobalt" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <SectionHeader
        title="Roles & Permissions"
        description={`${roles.length} roles configured`}
        icon={<Shield className="h-5 w-5" />}
        actions={(
          <>
            <Button variant="ghost" onClick={() => void refetch()} icon={<RefreshCw className="h-4 w-4" />}>
              Refresh
            </Button>
            <Button variant="ghost" onClick={handleCreate} icon={<Plus className="h-4 w-4" />}>
              New Role
            </Button>
          </>
        )}
      />

      {(error || actionError) && (
        <AlertBanner tone="error" title="Error">
          {actionError || error}
        </AlertBanner>
      )}

      <RoleList
        roles={sortedRoles}
        actionLoadingId={actionLoading}
        onEdit={handleEdit}
        onDuplicate={handleDuplicate}
        onDelete={setDeleteTarget}
      />

      {editorOpen && (
        <RoleEditor roleId={editingRoleId} onClose={handleEditorClose} onSave={handleEditorSave} />
      )}

      <ConfirmDialog
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={confirmDelete}
        title="Delete role"
        message={
          deleteTarget
            ? `Delete role "${deleteTarget.display_name}"? Users with this role will lose its permissions.`
            : ''
        }
        confirmLabel="Delete"
        variant="danger"
        loading={actionLoading === deleteTarget?.id}
      />
    </div>
  );
}
