import { useCallback, useMemo } from 'react';
import { useAuth } from '../auth/AuthContext';
import type { PermissionsSummary, PermissionAction, FieldPermissionSummary, FormField } from '../types';

interface UsePermissionsResult {
  permissions: PermissionsSummary | null;
  loading: boolean;
  error: string | null;

  can: (action: PermissionAction, entityType: string) => boolean;
  hasPermission: (key: string) => boolean;

  canViewField: (entityType: string, fieldName: string) => boolean;
  canEditField: (entityType: string, fieldName: string) => boolean;
  shouldMaskField: (entityType: string, fieldName: string) => boolean;

  getFieldPermissions: (entityType: string) => Record<string, FieldPermissionSummary>;
  filterVisibleFields: (entityType: string, fields: FormField[]) => FormField[];
  filterEditablePayload: (entityType: string, data: Record<string, unknown>) => Record<string, unknown>;

  refetch: () => Promise<void>;
}

export function usePermissions(): UsePermissionsResult {
  const { permissions, isLoading, refreshPermissions } = useAuth();

  const isSuperAdmin = permissions?.roles.some((r) => r.name === 'superadmin') ?? false;

  const hasPermission = useCallback(
    (key: string): boolean => {
      if (!permissions) return true;
      if (isSuperAdmin) return true;
      if (permissions.roles.length === 0) return true;
      return permissions.permissions.includes(key);
    },
    [permissions, isSuperAdmin],
  );

  const can = useCallback(
    (action: PermissionAction, entityType: string): boolean => {
      if (!permissions) return true;
      if (isSuperAdmin) return true;
      if (permissions.roles.length === 0) return true;

      const entityPerms = permissions.entity_permissions[entityType];
      if (entityPerms && entityPerms[action]) return true;

      const wildcardPerms = permissions.entity_permissions['*'];
      if (wildcardPerms && wildcardPerms[action]) return true;

      return false;
    },
    [permissions, isSuperAdmin],
  );

  const getFieldPerms = useCallback(
    (entityType: string): Record<string, FieldPermissionSummary> => {
      if (!permissions) return {};
      return permissions.field_permissions[entityType] || {};
    },
    [permissions],
  );

  const canViewField = useCallback(
    (entityType: string, fieldName: string): boolean => {
      if (isSuperAdmin) return true;
      const fieldPerms = getFieldPerms(entityType);
      if (Object.keys(fieldPerms).length === 0) return true;
      const fp = fieldPerms[fieldName];
      if (!fp) return false;
      return fp.can_view;
    },
    [getFieldPerms, isSuperAdmin],
  );

  const canEditField = useCallback(
    (entityType: string, fieldName: string): boolean => {
      if (isSuperAdmin) return true;
      const fieldPerms = getFieldPerms(entityType);
      if (Object.keys(fieldPerms).length === 0) return true;
      const fp = fieldPerms[fieldName];
      if (!fp) return false;
      return fp.can_edit;
    },
    [getFieldPerms, isSuperAdmin],
  );

  const shouldMaskField = useCallback(
    (entityType: string, fieldName: string): boolean => {
      if (isSuperAdmin) return false;
      const fieldPerms = getFieldPerms(entityType);
      const fp = fieldPerms[fieldName];
      if (!fp) return false;
      return fp.mask_value;
    },
    [getFieldPerms, isSuperAdmin],
  );

  const filterVisibleFields = useCallback(
    (entityType: string, fields: FormField[]): FormField[] => {
      if (isSuperAdmin) return fields;
      const fieldPerms = getFieldPerms(entityType);
      if (Object.keys(fieldPerms).length === 0) return fields;
      return fields.filter((f) => {
        const fp = fieldPerms[f.id];
        if (!fp) return false;
        return fp.can_view;
      });
    },
    [getFieldPerms, isSuperAdmin],
  );

  const filterEditablePayload = useCallback(
    (entityType: string, data: Record<string, unknown>): Record<string, unknown> => {
      return Object.fromEntries(
        Object.entries(data).filter(
          ([key]) => canEditField(entityType, key) && !shouldMaskField(entityType, key),
        ),
      );
    },
    [canEditField, shouldMaskField],
  );

  return useMemo(
    () => ({
      permissions,
      loading: isLoading,
      error: null,
      can,
      hasPermission,
      canViewField,
      canEditField,
      shouldMaskField,
      getFieldPermissions: getFieldPerms,
      filterVisibleFields,
      filterEditablePayload,
      refetch: refreshPermissions,
    }),
    [permissions, isLoading, can, hasPermission, canViewField, canEditField, shouldMaskField, getFieldPerms, filterVisibleFields, filterEditablePayload, refreshPermissions],
  );
}
