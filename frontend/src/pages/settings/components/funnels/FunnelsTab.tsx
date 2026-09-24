import { Loader2, AlertCircle, Lock, RefreshCw } from 'lucide-react';
import FunnelList from './FunnelList';
import { Button } from '@/components/ui/button';
import ConfirmDialog from '../../../../core/components/ConfirmDialog';
import { useFunnelList } from '../../../../core/hooks/useFunnelList';
import { usePermissions } from '../../../../core/hooks/usePermissions';

export default function FunnelsTab() {
  const { hasPermission } = usePermissions();
  const canWrite = hasPermission('workflow:write');

  const {
    records,
    loading,
    error,
    deleteTarget,
    deleteLoading,
    refetch,
    clearError,
    selectWorkflow,
    createWorkflow,
    duplicateWorkflow,
    requestDelete,
    cancelDelete,
    confirmDelete,
  } = useFunnelList();

  if (loading && records.length === 0) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (error && records.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <AlertCircle className="mb-4 h-12 w-12 text-destructive/70" />
        <p className="mb-4 text-destructive">{error}</p>
        <Button variant="ghost"
          onClick={refetch}
          icon={<RefreshCw className="w-4 h-4" />}
        >
          Retry
        </Button>
      </div>
    );
  }

  return (
    <>
      {!canWrite && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-warning/30 bg-warning-subtle p-3 text-warning text-sm">
          <Lock className="w-4 h-4 flex-shrink-0" />
          You have read-only access to Workflows. Contact an admin to make changes.
        </div>
      )}
      {error && (
        <div className="mb-4 rounded-lg border border-destructive/20 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
          <Button variant="primary" onClick={clearError} className="ml-2 underline">
            Dismiss
          </Button>
        </div>
      )}
      <FunnelList
        records={records}
        onSelect={selectWorkflow}
        onCreate={createWorkflow}
        onDuplicate={duplicateWorkflow}
        onDelete={requestDelete}
        loading={loading}
      />
      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete Workflow?"
        message={`Are you sure you want to delete "${deleteTarget?.name || deleteTarget?.machine_name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        variant="danger"
        loading={deleteLoading}
        onConfirm={confirmDelete}
        onClose={cancelDelete}
      />
    </>
  );
}
