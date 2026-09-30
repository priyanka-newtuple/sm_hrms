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
    queryFn: () => request<{ capabilities: string[]; roles: string[] }>('/hrms/capabilities'),
    staleTime: 0,
  });
}
