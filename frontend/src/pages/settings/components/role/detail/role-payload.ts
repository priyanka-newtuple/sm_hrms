import type { EntityPermission } from "@/core/types/rbac"
import { type EntityFilter, type FieldPermission } from "@/lib/entity-data"
import type { EntityConditionOperator, EntityPermissionCreate, FieldPermissionCreate, PermissionAction } from "@/core/types"

/** Load compound filters and legacy single conditions into the same editor shape. */
export function readEntityFilter(permission: EntityPermission): EntityFilter | undefined {
  if (permission.action !== "view") return undefined
  if (permission.read_filter) return permission.read_filter
  if (permission.entity_field && permission.operator && permission.condition_value != null) {
    return { conditions: [{
      conjunction: "AND",
      entity_field: permission.entity_field,
      operator: permission.operator as EntityConditionOperator,
      value_source: permission.value_source ?? "LITERAL",
      condition_value: permission.condition_value,
    }] }
  }
  return undefined
}

/** Splits a "entity_type:action" or "entity_type:field_name" composite key on its
 * first colon — entity type names never contain a colon themselves. */
function splitKey(key: string): [entityType: string, rest: string] {
  const idx = key.indexOf(':')
  return [key.slice(0, idx), key.slice(idx + 1)]
}

function serializeAppPermissions(granted: Set<string>) {
  return Array.from(granted).map((permission_key) => ({ permission_key }))
}

/** Entity-type permissions, with the `view` action's optional condition (entity
 * field permission filter) merged in. Drops any entry whose entity type is
 * confirmed stale (no longer in the org) rather than resubmitting it. */
function serializeEntityPermissions(
  entityPerms: Set<string>,
  entityConditions: Record<string, EntityFilter>,
  isKnownEntityType: (name: string) => boolean
): { entries: EntityPermissionCreate[]; staleKeys: string[] } {
  const parsed = Array.from(entityPerms).map((key) => {
    const [entity_type, action] = splitKey(key)
    return { entity_type, action: action as PermissionAction }
  })
  const staleKeys = parsed.filter((p) => !isKnownEntityType(p.entity_type)).map((p) => p.entity_type)
  const entries = parsed
    .filter((p) => isKnownEntityType(p.entity_type))
    .map(({ entity_type, action }) => {
      const condition = action === 'view' ? entityConditions[entity_type] : undefined
      return {
        entity_type,
        action,
        allowed: true as const,
        ...(condition && { read_filter: condition }),
      }
    })
  return { entries, staleKeys }
}

/** Per-field view/edit/mask permissions. Same stale-entity-type dropping as
 * entity permissions. */
function serializeFieldPermissions(
  fieldPerms: Record<string, FieldPermission>,
  isKnownEntityType: (name: string) => boolean
): { entries: FieldPermissionCreate[]; staleKeys: string[] } {
  const parsed = Object.entries(fieldPerms).map(([key, fp]) => {
    const [entity_type, field_name] = splitKey(key)
    return { entity_type, field_name, fp }
  })
  const staleKeys = parsed.filter((p) => !isKnownEntityType(p.entity_type)).map((p) => p.entity_type)
  const entries = parsed
    .filter((p) => isKnownEntityType(p.entity_type))
    .map(({ entity_type, field_name, fp }) => ({
      entity_type,
      field_name,
      can_view: fp.view,
      can_edit: fp.edit,
      mask_value: fp.mask,
    }))
  return { entries, staleKeys }
}

function serializeTransitionPermissions(transitionPerms: Set<string>) {
  return Array.from(transitionPerms).map((key) => {
    const [machine_name, transition_key] = splitKey(key)
    return { machine_name, transition_key }
  })
}

export interface RolePayloadState {
  granted: Set<string>
  entityPerms: Set<string>
  entityConditions: Record<string, EntityFilter>
  fieldPerms: Record<string, FieldPermission>
  transitionPerms: Set<string>
  workflowPerms: Set<string>
  isKnownEntityType: (name: string) => boolean
}

export interface RolePayload {
  permissions: { permission_key: string }[]
  entity_permissions: EntityPermissionCreate[]
  field_permissions: FieldPermissionCreate[]
  transition_permissions: { machine_name: string; transition_key: string }[]
  workflow_permissions: { machine_name: string }[]
}

/** Builds the save-ready role payload from editor working state, and reports
 * which entity types (if any) got silently dropped for being stale (no longer
 * in the org — see `isKnownEntityType`'s own docs at the call site). */
export function buildRolePayload(
  state: RolePayloadState
): { payload: RolePayload; staleEntityTypes: string[] } {
  const entity = serializeEntityPermissions(state.entityPerms, state.entityConditions, state.isKnownEntityType)
  const field = serializeFieldPermissions(state.fieldPerms, state.isKnownEntityType)
  const staleEntityTypes = Array.from(new Set([...entity.staleKeys, ...field.staleKeys]))

  return {
    payload: {
      permissions: serializeAppPermissions(state.granted),
      entity_permissions: entity.entries,
      field_permissions: field.entries,
      transition_permissions: serializeTransitionPermissions(state.transitionPerms),
      workflow_permissions: Array.from(state.workflowPerms).map((machine_name) => ({ machine_name })),
    },
    staleEntityTypes,
  }
}
