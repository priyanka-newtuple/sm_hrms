import { useQuery } from '@tanstack/react-query';
import { request } from '../../core/services/api/client';

export function useHrmsOrganization() {
  return useQuery({
    queryKey: ['hrms', 'organization'],
    queryFn: () => request<{id: string; name: string; slug: string; domain: string | null; status: string}>('/hrms/organization'),
  });
}

export function useHrmsCapabilities() {
  return useQuery({
    queryKey: ['hrms', 'capabilities'],
    // employee_profile: whether the account is linked to an employee, which self-service (leave) needs.
    queryFn: () => request<{ capabilities: string[]; roles: string[]; employee_profile?: boolean }>('/hrms/capabilities'),
    staleTime: 0,
  });
}
