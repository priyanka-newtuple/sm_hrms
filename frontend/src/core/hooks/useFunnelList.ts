import { useState, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import api from '../services/api';
import { useStateMachinesList, useInvalidateStateMachinesList, STATE_MACHINES_LIST_QUERY_KEY } from './useStateMachinesList';
import type { StateMachineRecord } from '../types';
import type { StateMachineDefinition } from '@/lib/state-machine/types';

interface UseFunnelListResult {
  records: StateMachineRecord[];
  loading: boolean;
  error: string | null;
  deleteTarget: StateMachineRecord | null;
  deleteLoading: boolean;

  refetch: () => Promise<void>;
  clearError: () => void;

  selectWorkflow: (record: StateMachineRecord) => void;
  createWorkflow: (mode: 'canvas' | 'wizard') => void;
  duplicateWorkflow: (record: StateMachineRecord) => Promise<void>;

  requestDelete: (record: StateMachineRecord) => void;
  cancelDelete: () => void;
  confirmDelete: () => Promise<void>;
}

function dedupeRecords(items: StateMachineRecord[]): StateMachineRecord[] {
  const publishedByMachine = new Map<string, StateMachineRecord>();
  const draftRows: StateMachineRecord[] = [];
  for (const r of items) {
    if (!r.is_active && r.version === 0) {
      draftRows.push(r);
    } else {
      const existing = publishedByMachine.get(r.machine_name);
      if (!existing || r.version > existing.version) {
        publishedByMachine.set(r.machine_name, r);
      }
    }
  }
  return [...publishedByMachine.values(), ...draftRows];
}

/**
 * Hook for managing the workflow (state machine) list page.
 *
 * Loads workflow records, dedupes drafts/published versions, and exposes
 * actions for selecting, creating, duplicating, and archiving workflows.
 * Owns loading/error state and a delete-confirmation target so consumers
 * render a unified UX without juggling multiple async sources.
 *
 * @returns {@link UseFunnelListResult} - records, async state, and action handlers.
 */
export function useFunnelList(): UseFunnelListResult {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data, isLoading, error: queryError, refetch: refetchQuery } = useStateMachinesList();
  const invalidate = useInvalidateStateMachinesList();

  // Fetch errors surface from the shared query; action errors (duplicate,
  // delete, navigation validation) are this hook's own concern and take
  // precedence since they're what the user just tried to do.
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<StateMachineRecord | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  const records = useMemo(() => dedupeRecords(data ?? []), [data]);
  const loading = isLoading || actionLoading;
  const error =
    actionError ?? (queryError ? (queryError instanceof Error ? queryError.message : 'Failed to load workflows') : null);

  const refetch = useCallback(async () => {
    await refetchQuery();
  }, [refetchQuery]);

  const clearError = useCallback(() => setActionError(null), []);

  const selectWorkflow = useCallback((record: StateMachineRecord) => {
    if (!record.id) {
      setActionError(`Workflow "${record.machine_name}" is missing an id; cannot open.`);
      return;
    }
    navigate(`/funnel/${encodeURIComponent(record.id)}/edit?view=wizard`);
  }, [navigate]);

  const createWorkflow = useCallback((mode: 'canvas' | 'wizard' = 'canvas') => {
    navigate(`/funnel/create?view=${mode}`);
  }, [navigate]);

  const duplicateWorkflow = useCallback(async (record: StateMachineRecord) => {
    try {
      setActionLoading(true);
      setActionError(null);
      const active = await api.stateMachines.getActive(record.machine_name);
      const def = active.definition as unknown as StateMachineDefinition;
      const timestamp = Date.now().toString(36);
      const baseName = (active.name || active.machine_name).replace(/\s*\((?:Draft )?Copy.*\)$/, '');
      const baseKey = active.machine_name.replace(/_copy_[a-z0-9]+$/, '');
      const draftCopyName = `${baseName} (Draft Copy)`;
      const copyName = `${baseName} (Copy)`;
      const copyKey = `${baseKey}_copy_${timestamp}`;

      const copyDef: StateMachineDefinition = {
        ...def,
        machine_key: copyKey,
        name: copyName,
        entity_schema: { ...def.entity_schema, entity_type: def.entity_type },
      };

      const draft = await api.stateMachines.createDraft({ name: draftCopyName });
      if (!draft.id) throw new Error('Draft creation response missing id.');
      const result = await api.stateMachines.publish(draft.id, copyDef);
      await invalidate();
      const newId = result?.state_machine?.id;
      if (!newId) {
        throw new Error('Publish response missing state_machine.id; cannot navigate.');
      }
      navigate(`/funnel/${encodeURIComponent(newId)}/edit?view=wizard`);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Failed to duplicate workflow');
    } finally {
      setActionLoading(false);
    }
  }, [navigate, invalidate]);

  const requestDelete = useCallback((record: StateMachineRecord) => {
    setDeleteTarget(record);
  }, []);

  const cancelDelete = useCallback(() => {
    setDeleteTarget(null);
  }, []);

  const confirmDelete = useCallback(async () => {
    if (!deleteTarget?.id) return;
    try {
      setDeleteLoading(true);
      setActionError(null);
      await api.stateMachines.delete(deleteTarget.id);
      // Optimistic cache update — instant removal from every consumer of the
      // shared list, without waiting on a full refetch round-trip.
      queryClient.setQueryData<StateMachineRecord[]>(
        STATE_MACHINES_LIST_QUERY_KEY,
        (prev) => (prev ?? []).filter((r) => r.id !== deleteTarget.id),
      );
      setDeleteTarget(null);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Failed to delete workflow');
      setDeleteTarget(null);
    } finally {
      setDeleteLoading(false);
    }
  }, [deleteTarget, queryClient]);

  return {
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
  };
}
