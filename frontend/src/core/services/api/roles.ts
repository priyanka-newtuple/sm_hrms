import type {
  Role,
  RoleListItem,
  RoleCreateRequest,
  RoleUpdateRequest,
  RoleDuplicateRequest,
  UserRoleRead,
  UserRoleSetRequest,
  PermissionsSummary,
  PermissionAction,
  RoleSummary,
  FieldPermissionSummary,
} from '../../types';
import { request } from './client';

interface RawPermissionsSummary {
  roles: RoleSummary[];
  permissions: string[];
  entity_permissions: Array<{ id: string; entity_type: string; action: string; allowed: boolean }>;
  field_permissions: Array<{ id: string; entity_type: string; field_name: string; can_view: boolean; can_edit: boolean; mask_value: boolean }>;
}

function transformPermissions(raw: RawPermissionsSummary): PermissionsSummary {
  const entity_permissions: Record<string, Record<PermissionAction, boolean>> = {};
  for (const ep of raw.entity_permissions) {
    if (!entity_permissions[ep.entity_type]) {
      entity_permissions[ep.entity_type] = {} as Record<PermissionAction, boolean>;
    }
    entity_permissions[ep.entity_type][ep.action as PermissionAction] = ep.allowed;
  }

  const field_permissions: Record<string, Record<string, FieldPermissionSummary>> = {};
  for (const fp of raw.field_permissions) {
    if (!field_permissions[fp.entity_type]) {
      field_permissions[fp.entity_type] = {};
    }
    field_permissions[fp.entity_type][fp.field_name] = {
      can_view: fp.can_view,
      can_edit: fp.can_edit,
      mask_value: fp.mask_value,
    };
  }

  return {
    roles: raw.roles,
    permissions: raw.permissions ?? [],
    entity_permissions,
    field_permissions,
  };
}

export const roles = {
  list: () =>
    request<RoleListItem[]>('/roles'),

  get: (roleId: string) =>
    request<Role>(`/roles/${roleId}`),

  create: (data: RoleCreateRequest) =>
    request<Role>('/roles', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (roleId: string, data: RoleUpdateRequest) =>
    request<Role>(`/roles/${roleId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  delete: (roleId: string) =>
    request<void>(`/roles/${roleId}`, {
      method: 'DELETE',
    }),

  duplicate: (roleId: string, data: RoleDuplicateRequest) =>
    request<Role>(`/roles/${roleId}/duplicate`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getUserRoles: (userId: string) =>
    request<UserRoleRead[]>(`/roles/users/${userId}/roles`),

  setUserRole: (userId: string, data: UserRoleSetRequest) =>
    request<UserRoleRead>(`/roles/users/${userId}/role`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  removeUserRole: (userId: string, roleId: string) =>
    request<void>(`/roles/users/${userId}/roles/${roleId}`, {
      method: 'DELETE',
    }),

  getMyPermissions: () =>
    request<RawPermissionsSummary>('/roles/my-permissions').then(transformPermissions),
};
