/**
 * useRoleEditor Hook
 *
 * Owns all data fetching, working state, and persistence for the role editor
 * wizard. Components consume the returned view-model and stay presentational.
 */

import { useState, useEffect, useMemo, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { roles as rolesApi, formSchemas } from '../services/api';
import { roleKeys } from '../services/api/queryKeys';
import { useSkin } from '../../skins';
import type {
  Role,
  EntityPermissionCreate,
  FieldPermissionCreate,
  PermissionAction,
  EntityPermMap,
  FieldPermMap,
  FieldPermState,
  EntityFieldMap,
} from '../types';

export const DEFAULT_PRIORITY = 50;
export const PRIORITY_MIN = 0;
export const PRIORITY_MAX = 100;

/** Canonical action keys, used to iterate permission maps. */
const ACTION_KEYS: PermissionAction[] = ['view', 'create', 'edit', 'delete', 'transition'];

const DEFAULT_FIELD_PERM: FieldPermState = { can_view: true, can_edit: true, mask_value: false };

interface RoleEditorForm {
  name: string;
  displayName: string;
  description: string;
  priority: number;
  isSystem: boolean;
}

export interface UseRoleEditorResult {
  // data
  form: RoleEditorForm;
  entityPerms: EntityPermMap;
  fieldPerms: FieldPermMap;
  entityTypes: { key: string; label: string }[];
  entityFields: EntityFieldMap;
  isEditing: boolean;
  // async state
  isLoading: boolean;
  isSaving: boolean;
  error: string | null;
  canSave: boolean;
  // basics actions
  setDisplayName: (value: string) => void;
  setName: (value: string) => void;
  setDescription: (value: string) => void;
  setPriority: (value: number) => void;
  // permission actions
  toggleEntityPerm: (entityType: string, action: PermissionAction) => void;
  toggleAllForEntity: (entityType: string) => void;
  toggleAllForAction: (action: PermissionAction) => void;
  getFieldPerm: (entityType: string, fieldName: string) => FieldPermState;
  setFieldPerm: (entityType: string, fieldName: string, updates: Partial<FieldPermState>) => void;
  // persistence
  save: () => Promise<boolean>;
}

export function useRoleEditor(roleId: string | null): UseRoleEditorResult {
  const isEditing = roleId !== null;

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { skin } = useSkin();
  const entityTypes = useMemo(
    () => skin.entityTypes.map((et) => ({ key: et.entityType, label: et.labelPlural })),
    [skin.entityTypes],
  );

  // Basics
  const [name, setNameState] = useState('');
  const [displayName, setDisplayNameState] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState(DEFAULT_PRIORITY);
  const [isSystem, setIsSystem] = useState(false);

  const [entityPerms, setEntityPerms] = useState<EntityPermMap>({});
  const [fieldPerms, setFieldPerms] = useState<FieldPermMap>({});

  const { data: schemasData } = useQuery({
    queryKey: ['formSchemas', 'list'],
    queryFn: () => formSchemas.list(undefined),
  });

  // Derive entity fields from active schemas.
  const entityFields = useMemo<EntityFieldMap>(() => {
    if (!schemasData) return {};
    const fieldMap: EntityFieldMap = {};
    for (const schema of schemasData.items) {
      if (!schema.is_active) continue;
      const fields = schema.schema.fields
        .filter((f) => f.type !== 'section' && f.type !== 'reference')
        .map((f) => ({ key: f.id, label: f.label }));
      if (fields.length > 0) fieldMap[schema.entity_type] = fields;
    }
    return fieldMap;
  }, [schemasData]);

  const { data: roleData, isLoading: loading } = useQuery({
    queryKey: roleKeys.detail(roleId!),
    queryFn: () => rolesApi.get(roleId!),
    enabled: !!roleId,
  });

  // Seed form state when role data loads.
  useEffect(() => {
    if (!roleData) {
      if (!roleId) {
        const defaults: EntityPermMap = {};
        for (const et of entityTypes) {
          defaults[et.key] = { view: true, create: false, edit: false, delete: false, transition: false };
        }
        setEntityPerms(defaults);
      }
      return;
    }

    const role: Role = roleData;
    setNameState(role.name);
    setDisplayNameState(role.display_name);
    setDescription(role.description || '');
    setPriority(role.priority);
    setIsSystem(role.is_system);

    const ep: EntityPermMap = {};
    for (const et of entityTypes) {
      ep[et.key] = { view: false, create: false, edit: false, delete: false, transition: false };
    }
    for (const perm of role.entity_permissions) {
      if (ep[perm.entity_type]) {
        ep[perm.entity_type][perm.action] = perm.allowed;
      } else if (perm.entity_type === '*') {
        for (const et of entityTypes) {
          ep[et.key][perm.action] = perm.allowed;
        }
      }
    }
    setEntityPerms(ep);

    const fp: FieldPermMap = {};
    for (const perm of role.field_permissions) {
      if (!fp[perm.entity_type]) fp[perm.entity_type] = {};
      fp[perm.entity_type][perm.field_name] = {
        can_view: perm.can_view,
        can_edit: perm.can_edit,
        mask_value: perm.mask_value,
      };
    }
    setFieldPerms(fp);
  }, [roleData, roleId, entityTypes]);

  // Auto-generate the system name from the display name (new roles only).
  const setDisplayName = useCallback(
    (value: string) => {
      setDisplayNameState(value);
      if (!isEditing) {
        setNameState(value.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, ''));
      }
    },
    [isEditing],
  );

  const setName = useCallback((value: string) => setNameState(value), []);

  const toggleEntityPerm = useCallback((entityType: string, action: PermissionAction) => {
    setEntityPerms((prev) => ({
      ...prev,
      [entityType]: {
        ...prev[entityType],
        [action]: !prev[entityType]?.[action],
      },
    }));
  }, []);

  const toggleAllForEntity = useCallback((entityType: string) => {
    setEntityPerms((prev) => {
      const current = prev[entityType];
      const allEnabled = !!current && ACTION_KEYS.every((a) => current[a]);
      return {
        ...prev,
        [entityType]: ACTION_KEYS.reduce(
          (acc, a) => ({ ...acc, [a]: !allEnabled }),
          {} as Record<PermissionAction, boolean>,
        ),
      };
    });
  }, []);

  const toggleAllForAction = useCallback(
    (action: PermissionAction) => {
      setEntityPerms((prev) => {
        const allEnabled = entityTypes.every((et) => prev[et.key]?.[action]);
        const next = { ...prev };
        for (const et of entityTypes) {
          next[et.key] = { ...next[et.key], [action]: !allEnabled };
        }
        return next;
      });
    },
    [entityTypes],
  );

  const getFieldPerm = useCallback(
    (entityType: string, fieldName: string): FieldPermState =>
      fieldPerms[entityType]?.[fieldName] || DEFAULT_FIELD_PERM,
    [fieldPerms],
  );

  const setFieldPerm = useCallback(
    (entityType: string, fieldName: string, updates: Partial<FieldPermState>) => {
      setFieldPerms((prev) => ({
        ...prev,
        [entityType]: {
          ...prev[entityType],
          [fieldName]: {
            ...(prev[entityType]?.[fieldName] || DEFAULT_FIELD_PERM),
            ...updates,
          },
        },
      }));
    },
    [],
  );

  const canSave = displayName.trim().length > 0 && name.trim().length > 0;

  const save = useCallback(async (): Promise<boolean> => {
    try {
      setSaving(true);
      setError(null);

      // Only persist allowed permissions.
      const entity_permissions: EntityPermissionCreate[] = [];
      for (const [entityType, actions] of Object.entries(entityPerms)) {
        for (const [action, allowed] of Object.entries(actions)) {
          if (allowed) {
            entity_permissions.push({ entity_type: entityType, action: action as PermissionAction, allowed: true });
          }
        }
      }

      // Only persist field permissions that restrict something (non-default).
      const field_permissions: FieldPermissionCreate[] = [];
      for (const [entityType, fields] of Object.entries(fieldPerms)) {
        for (const [fieldName, fp] of Object.entries(fields)) {
          if (!fp.can_view || !fp.can_edit || fp.mask_value) {
            field_permissions.push({
              entity_type: entityType,
              field_name: fieldName,
              can_view: fp.can_view,
              can_edit: fp.can_edit,
              mask_value: fp.mask_value,
            });
          }
        }
      }

      if (isEditing && roleId) {
        await rolesApi.update(roleId, {
          name,
          display_name: displayName,
          description: description || undefined,
          priority,
          entity_permissions,
          field_permissions,
        });
      } else {
        await rolesApi.create({
          name,
          display_name: displayName,
          description: description || undefined,
          priority,
          entity_permissions,
          field_permissions,
        });
      }

      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save role');
      return false;
    } finally {
      setSaving(false);
    }
  }, [entityPerms, fieldPerms, isEditing, roleId, displayName, description, priority, name]);

  return {
    form: { name, displayName, description, priority, isSystem },
    entityPerms,
    fieldPerms,
    entityTypes,
    entityFields,
    isEditing,
    isLoading: loading || false,
    isSaving: saving,
    error,
    canSave,
    setDisplayName,
    setName,
    setDescription,
    setPriority,
    toggleEntityPerm,
    toggleAllForEntity,
    toggleAllForAction,
    getFieldPerm,
    setFieldPerm,
    save,
  };
}
