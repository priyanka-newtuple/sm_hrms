import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/core/auth';
import { stateMachines } from '@/core/services/api/stateMachines';

/** Native, human-authorized definitions; never infer the catalog from populated records. */
export function useWorkflowCatalog(enabled = true) {
  const { user, permissions } = useAuth();
  return useQuery({
    queryKey: ['hrms', 'workflow-catalog', user?.organizationId, user?.id],
    enabled: enabled && Boolean(permissions?.permissions.includes('workflow:read')),
    queryFn: async () => {
      const records = await stateMachines.listPublished();
      const latest = new Map<string, typeof records[number]>();
      for (const record of records) {
        if (!record.is_active) continue;
        const previous = latest.get(record.machine_name);
        if (!previous || previous.version < record.version) latest.set(record.machine_name, record);
      }
      return [...latest.values()].sort((a, b) => a.name.localeCompare(b.name));
    },
  });
}
