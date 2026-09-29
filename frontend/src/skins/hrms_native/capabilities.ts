import { useQuery } from '@tanstack/react-query';
import { request } from '../../core/services/api/client';

export function useHrmsCapabilities() {
  return useQuery({
    queryKey: ['hrms', 'capabilities'],
    queryFn: () => request<{ capabilities: string[]; roles: string[] }>('/hrms/capabilities'),
    staleTime: 0,
  });
}
