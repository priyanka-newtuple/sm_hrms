import { useMemo, useState } from 'react';
import FunnelListHeader from './FunnelListHeader';
import FunnelListFilterBar, { type StatusFilter, type OwnerOption } from './FunnelListFilterBar';
import FunnelListTable from './FunnelListTable';
import WorkflowServicePanel from './WorkflowServicePanel';
import { useWorkflowServices } from './useWorkflowServices';
import ConfirmDialog from '../../../../core/components/ConfirmDialog';
import { usePermissions } from '../../../../core/hooks/usePermissions';
import type { StateMachineRecord, WorkflowService } from '../../../../core/types';

const UNKNOWN_OWNER_ID = '__unknown__';

/**
 * Returns the canonical owner id for a workflow record, falling back to a
 * sentinel when no owner is recorded.
 */
function ownerIdFor(record: StateMachineRecord): string {
  return record.created_by || UNKNOWN_OWNER_ID;
}

interface FunnelListProps {
  records: StateMachineRecord[];
  onSelect: (record: StateMachineRecord) => void;
  onCreate: (mode: 'canvas' | 'wizard') => void;
  onDuplicate?: (record: StateMachineRecord) => void;
  onDelete?: (record: StateMachineRecord) => void;
  loading?: boolean;
}

export default function FunnelList({
  records,
  onSelect,
  onCreate,
  onDuplicate,
  onDelete,
  loading,
}: FunnelListProps) {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [search, setSearch] = useState('');
  const [ownerFilter, setOwnerFilter] = useState<Set<string>>(new Set());
  const [versionFilter, setVersionFilter] = useState<Set<number>>(new Set());

  const { hasPermission } = usePermissions();
  const canWriteServices = hasPermission('workflow:write');
  const [servicePanelOpen, setServicePanelOpen] = useState(false);
  const [pendingServiceDelete, setPendingServiceDelete] = useState<WorkflowService | null>(null);
  const {
    services,
    savingService,
    deletingService,
    handleCreateService,
    handleRenameService,
    handleDeleteService,
  } = useWorkflowServices();

  const counts = useMemo(() => ({
    all: records.length,
    active: records.filter(r => r.is_active).length,
    draft: records.filter(r => !r.is_active).length,
  }), [records]);

  const owners = useMemo<OwnerOption[]>(() => {
    const byId = new Map<string, string>();
    for (const r of records) {
      byId.set(ownerIdFor(r), r.created_by_name || (r.created_by ? r.created_by : 'Unknown'));
    }
    return [...byId.entries()]
      .map(([id, name]) => ({ id, name }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [records]);

  const versions = useMemo(
    () => [...new Set(records.map(r => r.version))].sort((a, b) => a - b),
    [records],
  );

  const filtered = useMemo(() => records.filter(r => {
    if (statusFilter === 'active' && !r.is_active) return false;
    if (statusFilter === 'draft' && r.is_active) return false;
    if (ownerFilter.size > 0 && !ownerFilter.has(ownerIdFor(r))) return false;
    if (versionFilter.size > 0 && !versionFilter.has(r.version)) return false;
    if (search.trim()) {
      const q = search.toLowerCase();
      return (
        (r.name || r.machine_name).toLowerCase().includes(q) ||
        r.machine_name.toLowerCase().includes(q) ||
        r.description?.toLowerCase().includes(q)
      );
    }
    return true;
  }), [records, statusFilter, search, ownerFilter, versionFilter]);

  return (
    <div className="space-y-0">
      <FunnelListHeader
        activeCount={counts.active}
        draftCount={counts.draft}
        loading={loading}
        onCreate={onCreate}
        onManageServices={() => setServicePanelOpen(true)}
      />
      <WorkflowServicePanel
        open={servicePanelOpen}
        onClose={() => setServicePanelOpen(false)}
        services={services}
        canWrite={canWriteServices}
        savingService={savingService}
        deletingService={deletingService}
        onCreateService={handleCreateService}
        onRenameService={handleRenameService}
        onDeleteService={(service) => setPendingServiceDelete(service)}
      />
      <ConfirmDialog
        open={!!pendingServiceDelete}
        title="Delete Service?"
        message={`Are you sure you want to delete "${pendingServiceDelete?.name}"? Workflows filed under it will need a new service. This action cannot be undone.`}
        confirmLabel="Delete"
        variant="danger"
        loading={!!pendingServiceDelete && deletingService === pendingServiceDelete.service_id}
        onConfirm={async () => {
          if (!pendingServiceDelete) return;
          if (await handleDeleteService(pendingServiceDelete.service_id)) setPendingServiceDelete(null);
        }}
        onClose={() => setPendingServiceDelete(null)}
      />
      <FunnelListFilterBar
        statusFilter={statusFilter}
        onStatusFilterChange={setStatusFilter}
        search={search}
        onSearchChange={setSearch}
        counts={counts}
        owners={owners}
        ownerFilter={ownerFilter}
        onOwnerFilterChange={setOwnerFilter}
        versions={versions}
        versionFilter={versionFilter}
        onVersionFilterChange={setVersionFilter}
      />
      <FunnelListTable
        records={filtered}
        totalRecords={records.length}
        onSelect={onSelect}
        onCreate={onCreate}
        onDuplicate={onDuplicate}
        onDelete={onDelete}
      />
    </div>
  );
}
