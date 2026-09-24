/**
 * RBAC (Role-Based Access Control) Types
 */

// Permission actions
export type PermissionAction = 'view' | 'create' | 'edit' | 'delete' | 'transition';

// --- Role types ---

/** App-level permission (e.g. "user:read") — backed by permission_key. */
export interface AppPermission {
  permission_key: string;
}

/** Supported comparison operators for an entity permission's read-narrowing condition
 * (entity field permission filter) — mirrors backend `EntityConditionOperator`. */
export const ENTITY_CONDITION_OPERATORS = ['==', '!=', 'in', 'not_in'] as const;
export type EntityConditionOperator = (typeof ENTITY_CONDITION_OPERATORS)[number];

/** The first connector is ignored; subsequent AND connectors bind before OR. */
export interface EntityCondition {
  conjunction: "AND" | "OR";
  entity_field: string;
  operator: EntityConditionOperator;
  value_source: string;
  condition_value: string;
}

export interface EntityFilter {
  conditions: EntityCondition[];
}

/** Entity CRUD permission (e.g. Candidate:view), optionally narrowed by a read
 * condition — a field/operator/value on the *view* action only (entity field
 * permission filter). All four condition fields are null/omitted together;
 * a configured condition always has all four set. */
export interface EntityPermission {
  id: string;
  entity_type: string;
  action: PermissionAction;
  allowed: boolean;
  entity_field?: string | null;
  operator?: string | null;
  value_source?: string | null;
  condition_value?: string | null;
  read_filter?: EntityFilter | null;
}

export interface FieldPermission {
  id: string;
  entity_type: string;
  field_name: string;
  can_view: boolean;
  can_edit: boolean;
  mask_value: boolean;
}

export interface TransitionPermission {
  id: string;
  machine_name: string;
  transition_key: string;
}

export interface WorkflowPermission {
  id: string;
  machine_name: string;
}

export interface Role {
  id: string;
  organization_id: string;
  name: string;
  display_name: string;
  description: string | null;
  is_system: boolean;
  priority: number;
  color: string | null;
  permissions: AppPermission[];
  entity_permissions: EntityPermission[];
  field_permissions: FieldPermission[];
  transition_permissions: TransitionPermission[];
  workflow_permissions: WorkflowPermission[];
  user_count?: number;
  created_at: string;
  updated_at: string | null;
}

export interface RoleListItem {
  id: string;
  name: string;
  display_name: string;
  description: string | null;
  is_system: boolean;
  priority: number;
  color: string | null;
  user_count: number;
  created_at: string;
}

// --- Role editor working-state types ---
// Mutable maps used by the role editor wizard before serialization to
// RolePermissionCreate / FieldPermissionCreate on save.

export interface FieldPermState {
  can_view: boolean;
  can_edit: boolean;
  mask_value: boolean;
}

/** entity_type -> action -> allowed */
export type EntityPermMap = Record<string, Record<PermissionAction, boolean>>;

/** entity_type -> field_name -> state */
export type FieldPermMap = Record<string, Record<string, FieldPermState>>;

/** A data field of an entity type, derived from its active form schema. */
export interface EntityFieldDef {
  key: string;
  label: string;
}

/** entity_type -> data fields */
export type EntityFieldMap = Record<string, EntityFieldDef[]>;

// --- Create/Update request types ---

/** App-level permission key for create requests (e.g. {permission_key: "user:read"}). */
export interface AppPermissionCreate {
  permission_key: string;
}

export interface EntityPermissionCreate {
  entity_type: string;
  action: PermissionAction;
  allowed: boolean;
  entity_field?: string | null;
  operator?: string | null;
  value_source?: string | null;
  condition_value?: string | null;
  read_filter?: EntityFilter | null;
}

export interface FieldPermissionCreate {
  entity_type: string;
  field_name: string;
  can_view: boolean;
  can_edit: boolean;
  mask_value: boolean;
}

export interface RoleCreateRequest {
  name: string;
  display_name: string;
  description?: string;
  priority?: number;
  color?: string;
  permissions?: AppPermissionCreate[];
  entity_permissions?: EntityPermissionCreate[];
  field_permissions?: FieldPermissionCreate[];
  transition_permissions?: { machine_name: string; transition_key: string }[];
  workflow_permissions?: { machine_name: string }[];
}

export interface RoleUpdateRequest {
  name?: string;
  display_name?: string;
  description?: string;
  priority?: number;
  color?: string;
  permissions?: AppPermissionCreate[];
  entity_permissions?: EntityPermissionCreate[];
  field_permissions?: FieldPermissionCreate[];
  transition_permissions?: { machine_name: string; transition_key: string }[];
  workflow_permissions?: { machine_name: string }[];
}

/** @deprecated Use AppPermissionCreate / EntityPermissionCreate instead */
export type RolePermissionCreate = EntityPermissionCreate;

export interface RoleDuplicateRequest {
  name: string;
  display_name: string;
}

// --- User role assignment ---

export interface UserRoleRead {
  id: string;
  user_id: string;
  organization_id: string;
  role_id: string;
  role_name: string;
  role_display_name: string;
  role_color: string | null;
  role_is_system: boolean;
  assigned_at: string;
  assigned_by: string | null;
}

export interface UserRoleSetRequest {
  role_id: string;
}

// --- Permissions summary (from /roles/my-permissions) ---

export interface FieldPermissionSummary {
  can_view: boolean;
  can_edit: boolean;
  mask_value: boolean;
}

export interface RoleSummary {
  id: string;
  name: string;
  display_name: string;
  priority: number;
  color: string | null;
  is_system: boolean;
}

export interface PermissionsSummary {
  roles: RoleSummary[];
  permissions: string[];
  entity_permissions: Record<string, Record<PermissionAction, boolean>>;
  field_permissions: Record<string, Record<string, FieldPermissionSummary>>;
}
