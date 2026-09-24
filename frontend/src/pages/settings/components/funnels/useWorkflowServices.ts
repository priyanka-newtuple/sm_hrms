/**
 * useWorkflowServices
 *
 * The service lookup list behind the "Service" picker on a workflow, plus its
 * CRUD mutations. Mirrors the category slice of the Method Library's
 * useMethods hook (create/rename/delete), scoped down to just this lookup
 * list since workflow records aren't denormalized with a service_name the way
 * methods are with category_name.
 */

import { useCallback, useEffect, useState } from 'react';
import { stateMachines } from '../../../../core/services/api';
import { getApiErrorMessage } from '../../../../core/services/api/client';
import type { WorkflowService } from '../../../../core/types';

export function useWorkflowServices() {
  const [services, setServices] = useState<WorkflowService[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savingService, setSavingService] = useState<string | null>(null);
  const [deletingService, setDeletingService] = useState<string | null>(null);

  const fetchServices = useCallback(async () => {
    setLoading(true);
    try {
      const res = await stateMachines.services.list();
      setServices(res.items);
      setError(null);
    } catch (e) {
      setError(getApiErrorMessage(e, 'Failed to load services'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchServices();
  }, [fetchServices]);

  async function handleCreateService(name: string) {
    try {
      const created = await stateMachines.services.create(name);
      setServices((prev) => [...prev, created].sort((a, b) => a.name.localeCompare(b.name)));
      setError(null);
      return created;
    } catch (e) {
      setError(getApiErrorMessage(e, 'Failed to create service'));
      return null;
    }
  }

  async function handleRenameService(serviceId: string, name: string) {
    setSavingService(serviceId);
    try {
      const updated = await stateMachines.services.rename(serviceId, name.trim());
      setServices((prev) =>
        prev.map((service) => (service.service_id === serviceId ? updated : service)),
      );
      setError(null);
      return true;
    } catch (e) {
      setError(getApiErrorMessage(e, 'Failed to rename service'));
      return false;
    } finally {
      setSavingService(null);
    }
  }

  async function handleDeleteService(serviceId: string) {
    setDeletingService(serviceId);
    try {
      await stateMachines.services.remove(serviceId);
      setServices((prev) => prev.filter((service) => service.service_id !== serviceId));
      setError(null);
      return true;
    } catch (e) {
      setError(getApiErrorMessage(e, 'Failed to delete service'));
      return false;
    } finally {
      setDeletingService(null);
    }
  }

  return {
    services,
    loading,
    error,
    savingService,
    deletingService,
    fetchServices,
    handleCreateService,
    handleRenameService,
    handleDeleteService,
  };
}
