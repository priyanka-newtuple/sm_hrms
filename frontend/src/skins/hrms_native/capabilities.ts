import { useQuery, useQueryClient } from '@tanstack/react-query';
import { request } from '../../core/services/api/client';

export function useHrmsOrganization() {
  return useQuery({
    queryKey: ['hrms', 'organization'],
    queryFn: () => request<{id: string; name: string; slug: string; domain: string | null; status: string}>('/hrms/organization'),
  });
}

type CapabilityResponse = { capabilities: string[]; roles: string[]; employee_profile?: boolean; permission_revision?: string };

export function useHrmsCapabilities() {
  const client = useQueryClient();
  return useQuery({
    queryKey: ['hrms', 'capabilities'],
    // employee_profile: whether the account is linked to an employee, which self-service (leave) needs.
    queryFn: async () => {
      const next = await request<CapabilityResponse>('/hrms/capabilities');
      const previous = client.getQueryData<CapabilityResponse>(['hrms', 'capabilities']);
      if (previous && previous.permission_revision !== next.permission_revision) {
        // Clear previously authorized data before refetching under changed native grants.
        // Do not reset this query itself, which would cause a refresh loop.
        void client.resetQueries({ predicate: query => query.queryKey[0] === 'hrms' && query.queryKey[1] !== 'capabilities' });
      }
      return next;
    },
    staleTime: 0,
    refetchInterval: 30_000,
    refetchOnWindowFocus: 'always',
  });
}
