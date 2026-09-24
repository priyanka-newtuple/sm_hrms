import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { roles as rolesApi } from '../services/api';
import { roleKeys } from '../services/api/queryKeys';
import type { Role, RoleListItem, RoleCreateRequest, RoleUpdateRequest, RoleDuplicateRequest } from '../types';

interface UseRolesReturn {
  roles: RoleListItem[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
  getRole: (roleId: string) => Promise<Role>;
  createRole: (data: RoleCreateRequest) => Promise<Role>;
  updateRole: (id: string, data: RoleUpdateRequest) => Promise<Role>;
  deleteRole: (id: string) => Promise<void>;
  duplicateRole: (id: string, data: RoleDuplicateRequest) => Promise<Role>;
}

export function useRoles(): UseRolesReturn {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: roleKeys.list() });

  const query = useQuery({
    queryKey: roleKeys.list(),
    queryFn: rolesApi.list,
  });

  const create = useMutation({
    mutationFn: (data: RoleCreateRequest) => rolesApi.create(data),
    onSuccess: invalidate,
  });

  const update = useMutation({
    mutationFn: ({ id, data }: { id: string; data: RoleUpdateRequest }) => rolesApi.update(id, data),
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: (id: string) => rolesApi.delete(id),
    onSuccess: invalidate,
  });

  const duplicate = useMutation({
    mutationFn: ({ id, data }: { id: string; data: RoleDuplicateRequest }) => rolesApi.duplicate(id, data),
    onSuccess: invalidate,
  });

  return {
    roles: query.data ?? [],
    loading: query.isLoading,
    error: query.error instanceof Error ? query.error.message : null,
    refetch: query.refetch,
    getRole: rolesApi.get,
    createRole: create.mutateAsync,
    updateRole: (id: string, data: RoleUpdateRequest) => update.mutateAsync({ id, data }),
    deleteRole: remove.mutateAsync,
    duplicateRole: (id: string, data: RoleDuplicateRequest) => duplicate.mutateAsync({ id, data }),
  };
}
