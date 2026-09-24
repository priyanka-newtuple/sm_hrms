/**
 * Decides whether a role may be offered a form field, as distinct from whether
 * it may read the value — the backend already enforces that per record.
 *
 * The form config endpoint returns every field regardless of role, so any UI
 * built from it has to re-apply permissions itself.
 */

import { useCallback } from 'react';

import type { FormField } from '../types';
import { usePermissions } from './usePermissions';

interface FormFieldOwner {
  entityType: string;
  fieldName: string;
}

/** An inherited field's permission row lives on its source type under its
 *  original name (`department` on `doctor`, not `doctor_department` on
 *  `patient`), so it has to be looked up there. */
function resolveFormFieldOwner(field: FormField, viewedEntityType: string): FormFieldOwner {
  if (field.type === 'reference' && field.source_entity && field.source_field) {
    return { entityType: field.source_entity, fieldName: field.source_field };
  }
  return { entityType: viewedEntityType, fieldName: field.id };
}

/**
 * Predicate: may the current actor be offered this field? The field's owning
 * entity type must be viewable, and the field must be viewable on that type.
 * Masked fields pass — a mask hides the value, not the field. Editability is
 * not consulted; this governs display only.
 *
 * `is_system` roles bypass: they are meant to see everything and are seeded
 * with no field permission rows, so the checks below would deny them. Tested
 * on `is_system` rather than reusing `canViewField`, which detects privilege by
 * the role name `superadmin` only and so misses `admin`.
 *
 * @param viewedEntityType Entity type whose form is being rendered.
 */
export function useFormFieldVisibility(viewedEntityType: string): (field: FormField) => boolean {
  const { permissions, can } = usePermissions();

  return useCallback(
    (field: FormField): boolean => {
      // Still loading, or the permissive default AuthContext sets when the
      // permissions request fails — never hide on unknown.
      if (!permissions || permissions.roles.length === 0) return true;
      if (permissions.roles.some((role) => role.is_system)) return true;

      const { entityType, fieldName } = resolveFormFieldOwner(field, viewedEntityType);
      if (!entityType || !fieldName) return true;

      if (!can('view', entityType)) return false;

      // Deny-by-default, matching the backend: no rows configured for the
      // owning type means no fields visible on it.
      const ownerFieldPermissions = permissions.field_permissions[entityType];
      if (!ownerFieldPermissions) return false;
      return ownerFieldPermissions[fieldName]?.can_view === true;
    },
    [permissions, can, viewedEntityType],
  );
}
