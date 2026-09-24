/**
 * Core Platform Types
 *
 * These types are domain-agnostic and represent the core state machine
 * platform concepts. They can be used by any domain pack (ATS, PMO, CRM, etc.)
 */

import type { ComponentType } from 'react';

import type { CalcNode } from '../../shared/utils/calc';

// Actor types for audit trails
export type ActorType = 'HUMAN' | 'AGENT' | 'SYSTEM' | 'INTEGRATION';

// Transition status
export type TransitionStatus = 'SUCCESS' | 'FAILED';

// Intervention types and statuses
export type InterventionKind = 'APPROVAL' | 'OVERRIDE' | 'PAUSE' | 'RESUME' | 'EDIT' | 'FORCE_TRANSITION';
export type InterventionStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'CANCELLED' | 'EXPIRED';

// Signal status
export type SignalStatus = 'PENDING' | 'FIRED' | 'CANCELLED';

// Core entity - domain-agnostic container for typed records
export interface Entity {
  entity_id: string;
  entity_type: string;
  schema_name: string;
  schema_version: number;
  data: Record<string, unknown>;
  owner_id?: string;
  created_at: string;
  updated_at: string;
  archived_at?: string;
}

// Entity state - current lifecycle pointer
export interface EntityState {
  entity_id: string;
  entity_type: string;
  machine_name: string;
  machine_version: number;
  state: string;
  state_entered_at: string;
  state_version: number;
  last_activity_at: string;
  sla_due_at?: string;
  risk?: string;
}

// Entity relation - graph edges between entities
export interface EntityRelation {
  relation_id: string;
  from_entity_id: string;
  from_entity_type: string;
  to_entity_id: string;
  to_entity_type: string;
  relation_type: string;
  relation_metadata: Record<string, unknown>;
  created_at: string;
}

// Relation declarations — field inheritance between entity types
export type RelationMode = 'REFERENCE' | 'SNAPSHOT';

export interface RelationDeclaration {
  relation_def_id: string;
  organization_id: string;
  from_entity_type_id: string;
  to_entity_type_id: string;
  relation_name: string | null;
  relation_type: RelationMode;
  relation_metadata: Record<string, unknown>;
  created_at: string | null;
  updated_at: string | null;
  deleted_at: string | null;
}

export interface RelationDeclarationListResponse {
  organization_id: string;
  items: RelationDeclaration[];
}

export interface RelatedEntityFile {
  file_id: string;
  type_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  storage_key: string;
  status: string;
  uploaded_by: string;
  owner_entity_id: string | null;
  owner_entity_type: string | null;
  storage_provider: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  relation_type: RelationMode;
  relation_def_id: string;
  source_entity_id: string;
  source_entity_type_id: string;
  source_entity_label: string;
}

export interface RelatedEntityFileGroup {
  source_entity_id: string;
  source_entity_type_id: string;
  source_entity_label: string;
  relation_type: RelationMode;
  relation_def_id: string;
  files: RelatedEntityFile[];
}

export interface RelatedEntityFileListResponse {
  organization_id: string;
  entity_id: string;
  configured: boolean;
  count: number;
  groups: RelatedEntityFileGroup[];
}

// Entity event - immutable audit log entry
export interface EntityEvent {
  event_id: string;
  entity_id: string;
  entity_type: string;
  event_type: string;
  actor_type: ActorType;
  actor_id: string;
  correlation_id?: string;
  idempotency_key?: string;
  payload: Record<string, unknown>;
  occurred_at: string;
}

// State transition - transition attempt log
export interface StateTransition {
  transition_id: string;
  entity_id: string;
  entity_type: string;
  from_state: string;
  to_state: string;
  trigger: string;
  actor_type: ActorType;
  actor_id: string;
  status: TransitionStatus;
  failure_code?: string;
  failure_detail?: string;
  guard_report?: Record<string, unknown>;
  inputs?: Record<string, unknown>;
  outputs?: Record<string, unknown>;
  correlation_id?: string;
  occurred_at: string;
}

// Intervention - HITL approval/override request
export interface Intervention {
  intervention_id: string;
  entity_id: string;
  entity_type: string;
  kind: InterventionKind;
  requested_by: string;
  assigned_to?: string;
  status: InterventionStatus;
  request_payload?: Record<string, unknown>;
  decision_payload?: Record<string, unknown>;
  reason?: string;
  requested_at: string;
  decided_at?: string;
}

// Signal - timer/SLA trigger
export interface Signal {
  signal_id: string;
  entity_id: string;
  entity_type: string;
  signal_type: string;
  due_at: string;
  status: SignalStatus;
  target_playbook?: string;
  payload?: Record<string, unknown>;
  fired_at?: string;
  created_at: string;
}

// API request/response types
export interface CreateEntityRequest {
  entity_type: string;
  schema_name: string;
  schema_version: number;
  data: Record<string, unknown>;
  owner_id?: string;
  machine_name?: string;
  machine_version?: number;
}

export interface TransitionRequest {
  entity_id: string;
  workflow_id?: string;
  trigger: string;
  inputs?: Record<string, unknown>;
  idempotency_key?: string;
}

export interface TransitionResponse {
  transition_id?: string;
  event_id?: string;
  status: TransitionStatus;
  from_state?: string;
  to_state?: string;
  state_version?: number;
  guard_report?: Array<{
    guard_type: string;
    passed: boolean;
    detail?: string;
    params?: Record<string, unknown>;
  }>;
  idempotent?: boolean;
  failure_code?: string;
  failure_detail?: string;
}

// Guard definition with evaluation status for UI display
export interface GuardDefinition {
  guard_type: string;
  params: Record<string, unknown>;
  description: string;
  passed: boolean;
  detail?: string;
}

// Available transition with guard evaluation results
export interface AvailableTransition {
  trigger: string;
  label?: string;
  to_state: string;
  guards: GuardDefinition[];
  /** Backend field: whether the transition may be executed now. */
  allowed?: boolean;
  /** False when field masking prevents a safe bulk readiness evaluation. */
  availability_known?: boolean;
  /** Legacy/derived flag kept for back-compat; may be undefined on the wire. */
  all_guards_passed?: boolean;
  blocked_reasons: string[];
}

// Response from GET /entities/{entity_id}/transitions/available
export interface AvailableTransitionsResponse {
  entity_id: string;
  current_state: string;
  available_transitions: AvailableTransition[];
}

// Preflight check types
export interface PreflightFieldRequirement {
  field: string;
  label?: string;
  type: string;
  required: boolean;
  current_value?: unknown;
  options?: string[];
}

export interface PreflightCommentConfig {
  required: boolean;
  label: string;
  placeholder: string;
  min_length?: number;
  roles: string[];
  existing_comment_id?: string;
  is_satisfied: boolean;
}

export interface PreflightResponse {
  entity_id: string;
  trigger: string;
  to_state: string;
  label?: string;
  required_fields: PreflightFieldRequirement[];
  prime_fields: PreflightFieldRequirement[];
  comment_config: PreflightCommentConfig;
  guards: GuardDefinition[];
  all_guards_passed: boolean;
  blocked_reasons: string[];
  needs_dialog: boolean;
}

// State machine definition (generic)
export interface StateMachineCanvasMetadata {
  nodes?: Record<string, { x: number; y: number }>;
  [key: string]: unknown;
}

export interface StateMachineRecord {
  id?: string;
  machine_key: string;
  machine_name: string;
  name: string;
  description?: string;
  entity_type: string;
  service_id?: string | null;
  version: number;
  is_active: boolean;
  definition: Record<string, unknown>;
  canvas_metadata?: StateMachineCanvasMetadata | null;
  organization_id: string;
  created_by?: string | null;
  created_by_name?: string | null;
  created_at: string;
}

// Projection types for analytics
export interface PipelineViewRead {
  application_id: string;
  candidate_id?: string;
  candidate_name?: string;
  candidate_email?: string;
  job_id?: string;
  job_title?: string;
  job_department?: string;
  machine_name?: string;
  machine_version?: number;
  current_state: string;
  state_entered_at: string;
  sla_due_at?: string;
  sla_risk?: 'CRITICAL' | 'WARNING' | 'OK';
  applied_at: string;
  updated_at: string;
}

export interface HeatmapRead {
  job_id: string;
  state: string;
  application_count: number;
  breached_count: number;
  avg_time_in_state_seconds?: number;
  updated_at: string;
}

export type {
  DashboardDefinitionRead,
  DashboardDefinitionUpdate,
  DashboardWidgetType,
  DashboardViz,
  DashboardWidgetLayout,
  DashboardWidgetDef,
  DashboardContentElement,
  DashboardConfig,
  DashboardFilterSource,
  DashboardMetricParamRead,
  DashboardMetricFieldRead,
  DashboardMetricRead,
  DashboardMetricsResponse,
  DashboardDataItem,
  DashboardDataRequest,
  DashboardSeriesPoint,
  DashboardTableColumn,
  DashboardWidgetData,
  DashboardDataResponse,
  DashboardFilterOption,
  DashboardFilterOptionsResponse,
  DashboardQueryFieldRead,
  DashboardQueryJoinRead,
  DashboardQuerySourceRead,
  DashboardQuerySourcesResponse,
  DashboardQuerySelectRequest,
  DashboardQueryJoinRequest,
  DashboardQueryFilterRequest,
  DashboardQueryAggregationRequest,
  DashboardQuerySortRequest,
  DashboardQueryDefinitionRequest,
  DashboardQueryPreviewResponse,
} from './dashboard';

// Re-export stage comment types for API convenience (deprecated, use Comment types)
export type {
  StageComment,
  StageCommentCreate,
  StageCommentUpdate,
  StageCommentListResponse,
  CommentRequirement,
  TransitionCommentRequirements,
  CommentRequirementCheck,
  CommentVisibility as StageCommentVisibility,
  EditHistoryEntry,
} from '../../domains/ats/types/stageComment';

// Re-export new unified comment types
export type {
  ApiEnvelope,
  Comment,
  CommentCreate,
  CommentUpdate,
  CommentReplyCreate,
  CommentListResponse,
  CommentVisibility,
  CommentEditHistoryEntry,
  MentionInfo,
  LikeSummary,
  UserSearchResult,
} from './comment';

// Re-export notification types
export type {
  Notification,
  NotificationListResponse,
  NotificationType,
  UnreadCountResponse,
  MarkAllReadResponse,
} from './notification';

// Re-export candidate like types
export type {
  CandidateLike,
  CandidateLikeSummary,
  CandidateLikeListResponse,
  CandidateLikeBulkItem,
  BulkLikesSummaryResponse,
} from './candidateLike';

// Re-export RBAC types
export type {
  PermissionAction,
  EntityPermission as RolePermissionType,
  FieldPermission as FieldPermissionType,
  EntityConditionOperator,
  Role,
  RoleListItem,
  EntityPermissionCreate,
  RolePermissionCreate,
  FieldPermissionCreate,
  FieldPermState,
  EntityPermMap,
  FieldPermMap,
  EntityFieldDef,
  EntityFieldMap,
  RoleCreateRequest,
  RoleUpdateRequest,
  RoleDuplicateRequest,
  UserRoleRead,
  UserRoleSetRequest,
  FieldPermissionSummary,
  RoleSummary,
  PermissionsSummary,
} from './rbac';
export { ENTITY_CONDITION_OPERATORS } from './rbac';

export type { CalcNode } from '../../shared/utils/calc';

export {
  CUSTOM_FORM_KEY_SEPARATOR,
  customFormValueKey,
  customFormValueKeys,
  customFormWritableColumns,
} from './customForms';
export type {
  CustomFormCell,
  CustomFormSchema,
  CustomFormSection,
} from './customForms';

// Form Configuration Types

// Field types for form builder
export type FieldType =
  | 'text'
  | 'textarea'
  | 'email'
  | 'phone'
  | 'number'
  | 'integer'
  | 'date'
  | 'datetime'
  | 'select'
  | 'multi_select'
  | 'picklist_multi'  // Frontend-only: picklist + multi-select toggle (backend stores as enum)
  | 'boolean'
  | 'url'
  | 'table'
  | 'auto_number'  // Backend-generated identifier with optional prefix/suffix
  | 'currency'  // Monetary value with configurable currency code
  | 'section'  // UI section placeholder (e.g., comments)
  | 'reference'  // Field from a related entity (read-only)
  | 'document'  // One or more uploaded files, stored as a list of file ids
  | 'timer_duration';  // Elapsed seconds recorded by the timer control, never typed directly

export type TableColumnType =
  | 'text'
  | 'textarea'
  | 'email'
  | 'phone'
  | 'number'
  | 'integer'
  | 'date'
  | 'datetime'
  | 'select'
  | 'multi_select'
  | 'boolean'
  | 'url'
  | 'percent'
  | 'currency';

export interface TableColumn {
  id: string;
  label: string;
  type: TableColumnType;
  required?: boolean;
  readonly?: boolean;
  placeholder?: string;
  enum_values?: string[];
  calc?: CalcNode;
  /** Same generic appearance override as `FormField.style_config`, applied to
   *  this column's cells (e.g. a textarea column's background/text color). */
  style_config?: {
    background_color?: string;
    text_color?: string;
  };
}

export interface TablePresetRow {
  id: string;
  label?: string;
  line?: string;
  readonly?: boolean;
  cells?: Record<string, unknown>;
  readonly_cells?: string[];
  cell_config?: Record<string, { type?: TableColumnType; calc?: CalcNode; readonly?: boolean }>;
}

export interface TableFieldConfig {
  row_mode?: 'dynamic' | 'fixed';
  display_mode?: 'grid' | 'form';
  allow_delete_rows?: boolean;
  min_rows?: number;
  max_rows?: number;
  columns?: TableColumn[];
  rows?: TablePresetRow[];
}

// Picklist option
export interface PicklistOption {
  value: string;
  label: string;
}

// Picklist for select/multi-select fields
export interface Picklist {
  id: string;
  name: string;
  options: PicklistOption[];
  created_at: string;
  updated_at: string;
}

// Form field definition
export interface FormField {
  id: string;
  label: string;
  type: FieldType;
  required: boolean;
  system: boolean;
  editable?: boolean;  // Whether field properties can be edited (default: true)
  placeholder?: string;
  /** Optional display unit for Integer fields, e.g. mg or samples. */
  unit?: string;
  picklist_id?: string;
  picklist_id_2?: string;  // Second picklist for picklist_multi (multi-select toggle part)
  enum_values?: string[];  // Inline options (stored values) for select/multi_select/dropdown part of picklist_multi
  enum_labels?: string[];  // Display labels parallel to enum_values (when picklist has separate label/value)
  enum_values_2?: string[];  // Multi-select toggle options for picklist_multi
  enum_labels_2?: string[];  // Display labels parallel to enum_values_2
  /**
   * picklist_multi only — "Extend Field". Maps an option of the second picklist
   * (a value from `enum_values_2`, never a label) to the Field Library fields
   * that appear once an end user selects that option. The key being present at
   * all — even as `{}` — is what marks Extend Field as ON.
   */
  extensions?: Record<string, FieldExtension>;
  /**
   * picklist_multi only — what the extension fields collect, in the admin's own
   * words ("Certificate", "Authority"). Drives the badges in steps 2 and 3.
   * Absent falls back to the generic "details" wording.
   */
  extension_label?: string;
  /**
   * picklist_multi only — the heading and description of each wizard step, in
   * the admin's own words. Unlike `extension_label` these apply whether or not
   * Extend Field is configured. Absent falls back to the generic wording.
   * Keep in step with `WIZARD_COPY_KEYS` in `./wizardCopy`, which is what the
   * mappers carry them by.
   */
  step1_label?: string;
  step1_description?: string;
  step2_label?: string;
  step2_description?: string;
  step3_label?: string;
  step3_description?: string;
  current_value?: unknown;
  min_value?: number;
  max_value?: number;
  max_length?: number;
  rows?: number;
  col_span?: 'full' | 'half';
  table_config?: TableFieldConfig;
  calc?: CalcNode;
  // Reference field options (for type=reference)
  source_entity?: string;  // Source entity type (e.g., 'ATS.Candidate')
  source_field?: string;   // Field ID on the source entity to display
  // Auto-number options (for type=auto_number) — value is generated by the backend
  auto_number_config?: {
    affix_mode?: 'none' | 'prefix' | 'suffix';
    affix?: string;
  };
  // Currency options (for type=currency)
  currency_config?: {
    currency_code?: string;  // ISO 4217 code, e.g. "USD", "EUR"
  };
  // Document options (for type=document). The file type decides where uploads
  // are stored (its metadata.storage_provider) and which extensions/size the
  // backend accepts, so a document field has to name one.
  document_config?: {
    type_id?: string;
    /** Allow more than one file. Defaults to true; the value is always a list. */
    multiple?: boolean;
  };
  /** Locks the field's *value* against edits at render time, independent of
   *  RBAC field permissions — e.g. a computed or reference-only field. Unlike
   *  `editable`, which gates the builder, this gates the entered value. */
  read_only?: boolean;
  /** Generic per-type appearance overrides, e.g. highlighting a textarea.
   *  Any CSS color string (hex, rgb, var(--token), …). Applied wherever the
   *  field type's renderer supports it. */
  style_config?: {
    background_color?: string;
    text_color?: string;
  };
}

/**
 * One Field Library field revealed by a picklist_multi option.
 *
 * A snapshot of the library field as it was when the administrator added it
 * (`toFormField()` output) plus the library id it came from, so a form renders
 * without resolving the library at runtime and a later library edit cannot
 * silently rewrite a saved form. `id` is the library field's `field_key` and is
 * the key the entered value is stored under.
 */
export interface ExtensionField extends FormField {
  library_field_id: string;
}

/** The fields one picklist_multi option reveals. */
export interface FieldExtension {
  fields: ExtensionField[];
}

// Form schema definition
export interface FormSchemaDefinition {
  fields: FormField[];
}

// Fields — org-wide catalogue of reusable field definitions
// (backend/field_library). `library_field_id` is the identifier consumers
// reference, `field_count_id` a sequential counter assigned by the database
// for display without exposing the UUID. Key never changes; name is
// editable in place (rename creates no version). Versioned content
// (field type, description, settings) lives on versions — a form links to a specific
// `version_id` and stays pinned to it even after a newer version exists.
export interface FieldTypeOption {
  code: string;
  label: string;
  engine_type: string | null;
  config_kind: string;
  selectable: boolean;
  unavailable_reason: string | null;
}

export interface FieldTypeCatalogueResponse {
  organization_id: string;
  items: FieldTypeOption[];
}

export interface FieldIdentity {
  library_field_id: string;
  field_count_id: number;
  organization_id: string;
  name: string;
  field_key: string;
  field_type: string;
  created_by?: string | null;
  created_by_name?: string | null;
  is_archived: boolean;
}

export interface FieldVersion {
  version_id: string;
  library_field_id: string;
  organization_id: string;
  version: number;
  /** Frozen identity name at the moment this version was created. */
  name: string;
  /** Frozen field type at the moment this version was created. */
  field_type: string;
  description?: string | null;
  settings: Record<string, unknown>;
  is_latest: boolean;
  created_by?: string | null;
  created_by_name?: string | null;
}

export interface FieldWithVersion {
  identity: FieldIdentity;
  version: FieldVersion;
}

export interface FieldListResponse {
  organization_id: string;
  items: FieldWithVersion[];
  total: number;
  limit: number;
  offset: number;
}

export interface FieldVersionListResponse {
  library_field_id: string;
  items: FieldVersion[];
}

export interface FieldCreateRequest {
  name: string;
  field_key: string;
  field_type: string;
  description?: string;
  settings?: Record<string, unknown>;
}

export interface FieldRenameRequest {
  name: string;
}

export interface FieldDescriptionUpdateRequest {
  description: string | null;
}

export interface FieldVersionCreateRequest {
  description?: string;
  settings?: Record<string, unknown>;
  field_type?: string;
}

// ── Method Library ────────────────────────────────────────────────────────────
// A method is a named, categorised, ordered list of fields drawn from the Field
// Library. Name/description/category are live editable state on the identity;
// the field list is versioned, so a workflow reading a method keeps the list it
// pinned. Each listed field also pins one field version, so it sees that field's
// type and settings as they were when the method version was made.

export interface MethodCategory {
  category_id: string;
  organization_id: string;
  name: string;
  created_at?: string | null;
}

export interface MethodIdentity {
  method_id: string;
  organization_id: string;
  /** Per-organization sequence number assigned by the database, never reused. */
  method_code: number;
  name: string;
  description?: string | null;
  category_id?: string | null;
  category_name?: string | null;
  created_by?: string | null;
  is_archived: boolean;
  created_at?: string | null;
  /** Entity types this method is offered on. Empty means offered nowhere. */
  entity_types: string[];
}

export interface MethodVersion {
  version_id: string;
  method_id: string;
  organization_id: string;
  version: number;
  is_latest: boolean;
  connector_id?: string | null;
  created_by?: string | null;
}

/** One field inside a method version, merged with its pinned Field Library
 *  shape: label/placeholder/required/position are the method's own view,
 *  field_key/field_type/settings come from the pinned field version. */
export interface MethodVersionField {
  id: string;
  method_version_id: string;
  library_field_id: string;
  field_version_id: string;
  label?: string | null;
  placeholder?: string | null;
  required: boolean;
  position: number;
  field_key: string;
  field_type: string;
  settings: Record<string, unknown>;
  /** Legacy per-usage inheritance (`"Type.field"`); projected into the
   *  relation's `relation_metadata` at publish, i.e. type-wide. */
  inherit_from?: string | null;
  /** `'inherited'`: this block's field takes its value from a linked record of
   *  `source_entity_type` (field `source_field_key`). Scoped to the workflows
   *  that pin this block, never written to `relation_metadata`. */
  ownership?: 'owned' | 'inherited' | null;
  source_entity_type?: string | null;
  source_field_key?: string | null;
}

export interface MethodWithFields {
  identity: MethodIdentity;
  version: MethodVersion;
  fields: MethodVersionField[];
}

export interface MethodCategoryListResponse {
  organization_id: string;
  items: MethodCategory[];
}

/** A grouping for workflows, unique by name within an organization. Mirrors
 *  MethodCategory exactly. */
export interface WorkflowService {
  service_id: string;
  organization_id: string;
  name: string;
  created_at?: string | null;
}

export interface WorkflowServiceListResponse {
  organization_id: string;
  items: WorkflowService[];
}

export interface MethodListResponse {
  organization_id: string;
  items: MethodIdentity[];
  total: number;
  limit: number;
  offset: number;
}

export interface MethodVersionListResponse {
  method_id: string;
  items: MethodVersion[];
  total: number;
  limit: number;
  offset: number;
}

/** One field as the caller wants it in a method. `version_id` omitted pins the
 *  field's current latest version at write time; given explicitly, that exact
 *  version is pinned (the backend rejects it if it belongs to a different
 *  field). Preserving the existing `field_version_id` on an edit is what keeps a
 *  pin from silently jumping to latest when the list is rewritten. */
export interface MethodFieldInput {
  library_field_id: string;
  version_id?: string | null;
  label?: string | null;
  placeholder?: string | null;
  required?: boolean;
  position?: number;
  inherit_from?: string | null;
  /** See MethodVersionField.ownership. The backend requires
   *  `source_entity_type` + `source_field_key` when this is `'inherited'`
   *  and refuses it together with `inherit_from`. */
  ownership?: 'owned' | 'inherited' | null;
  source_entity_type?: string | null;
  source_field_key?: string | null;
}

/** Moves one already-listed method field to a different version of that same
 *  field. Produces a new method version, like any other field-list change. */
export interface MethodFieldRepinRequest {
  version_id: string;
}

export interface MethodCreateRequest {
  name: string;
  description?: string | null;
  category_id?: string | null;
  fields?: MethodFieldInput[];
  /** Empty is allowed and leaves the method hidden from every state picker. */
  entity_types?: string[];
}

export interface MethodCloneRequest {
  name: string;
  /** Omitted clones the source's current latest version. */
  source_version_id?: string | null;
  /** Omitted inherits the source method's category. */
  category_id?: string | null;
}

/** Only the members present are applied, and none of it versions the method. */
export interface MethodMetadataUpdateRequest {
  name?: string;
  description?: string | null;
  category_id?: string | null;
  /** Omitted leaves tags untouched; a list (including []) replaces them. */
  entity_types?: string[];
}

/** A wholesale replacement of the field list, producing a new version. */
export interface MethodFieldListUpdateRequest {
  fields: MethodFieldInput[];
  connector_id?: string | null;
}

// Form schema record
export interface FormSchema {
  id: string;
  schema_key: string;
  name: string;
  entity_type: string;
  version: number;
  is_active: boolean;
  /** Sort position among forms sharing an entity_type; lower shows first. */
  display_order: number;
  schema: FormSchemaDefinition;
  created_at: string;
  updated_at: string;
}

// API request types
export interface PicklistCreateRequest {
  name: string;
  options: PicklistOption[];
}

export interface PicklistUpdateRequest {
  name?: string;
  options?: PicklistOption[];
}

export interface FormSchemaCreateRequest {
  name: string;
  entity_type: string;
  schema: FormSchemaDefinition;
  activate?: boolean;
}

export interface FormSchemaUpdateRequest {
  name?: string;
  schema?: FormSchemaDefinition;
  activate?: boolean;
}

// API response types
export interface PicklistListResponse {
  items: Picklist[];
  total: number;
}

export interface FormSchemaListResponse {
  items: FormSchema[];
  total: number;
}

// LLM API Key Configuration Types

export type LLMProvider =
  | 'openai'
  | 'anthropic'
  | 'google'
  | 'google_gemini'
  | 'azure_openai'
  | 'azure_foundry'
  | 'aws_bedrock';

export type LLMValidationStatus = 'valid' | 'invalid' | 'unknown';

export interface LLMApiKey {
  id: string;
  provider: LLMProvider;
  display_hint: string | null;
  is_active: boolean;
  validation_status: LLMValidationStatus | null;
  last_validated_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface LLMProviderInfo {
  id: LLMProvider;
  name: string;
  description: string;
  configured: boolean;
  validation_status: LLMValidationStatus | null;
}

export interface LLMApiKeyCreateRequest {
  provider: LLMProvider;
  api_key: string;
  validate?: boolean;
}

export interface LLMApiKeyValidateRequest {
  provider: LLMProvider;
  api_key: string;
}

export interface LLMApiKeyValidateResponse {
  provider: string;
  valid: boolean;
  message: string;
}

export interface LLMApiKeyListResponse {
  items: LLMApiKey[];
}

export interface LLMProvidersListResponse {
  providers: LLMProviderInfo[];
}

// Email Configuration Types

export type EmailProvider = 'ses' | 'smtp';

export type EmailValidationStatus = 'valid' | 'invalid' | 'unknown';

export interface EmailConfig {
  id: string;
  provider: EmailProvider;
  access_key_hint: string | null;
  // SES fields
  region: string | null;
  // SMTP fields
  smtp_host: string | null;
  smtp_port: number | null;
  smtp_use_tls: boolean | null;
  // Common fields
  from_email: string;
  from_name: string | null;
  reply_to_email: string | null;
  is_active: boolean;
  validation_status: EmailValidationStatus | null;
  last_validated_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface EmailProviderInfo {
  id: EmailProvider;
  name: string;
  description: string;
  configured: boolean;
  validation_status: EmailValidationStatus | null;
  from_email: string | null;
  // SES-specific
  region: string | null;
  // SMTP-specific
  smtp_host: string | null;
  smtp_port: number | null;
}

export interface EmailConfigCreateRequest {
  provider: EmailProvider;
  access_key_id: string;
  secret_access_key: string;
  // SES fields (required for 'ses' provider)
  region?: string;
  // SMTP fields (required for 'smtp' provider)
  smtp_host?: string;
  smtp_port?: number;
  smtp_use_tls?: boolean;
  // Common fields
  from_email: string;
  from_name?: string;
  reply_to_email?: string;
  validate?: boolean;
}

export interface EmailConfigValidateRequest {
  provider: EmailProvider;
  access_key_id: string;
  secret_access_key: string;
  // SES fields
  region?: string;
  // SMTP fields
  smtp_host?: string;
  smtp_port?: number;
  smtp_use_tls?: boolean;
  // Common
  from_email: string;
}

export interface EmailConfigValidateResponse {
  provider: string;
  valid: boolean;
  message: string;
}

export interface EmailConfigListResponse {
  items: EmailConfig[];
}

export interface EmailProvidersListResponse {
  providers: EmailProviderInfo[];
}

export interface EmailTestRequest {
  to_email: string;
}

export interface EmailTestResponse {
  success: boolean;
  message: string;
  message_id: string | null;
}

// Action Definition Types

export interface ActionDefinition {
  definition_id: string;
  kind: string;
  name: string;
  description: string | null;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  created_at: string;
}

export interface ActionDefinitionListResponse {
  items: ActionDefinition[];
}

// Email Template Types

export interface EmailTemplate {
  template_id: string;
  organization_id: string | null;
  name: string;
  subject: string;
  body_html: string;
  form_id: string | null;
  entity_type: string | null;
  is_system: boolean;
  created_at: string;
}

export interface EmailTemplateCreateRequest {
  name: string;
  subject: string;
  body_html: string;
  form_id?: string | null;
  entity_type?: string | null;
}

export interface EmailTemplateUpdateRequest {
  name: string;
  subject: string;
  body_html: string;
  form_id?: string | null;
  entity_type?: string | null;
}

export interface EmailTemplateListResponse {
  items: EmailTemplate[];
}

// Transcription Configuration Types

export type TranscriptionProvider = 'elevenlabs' | 'openai';

export type TranscriptionValidationStatus = 'valid' | 'invalid' | 'unknown';

export interface TranscriptionConfig {
  id: string;
  provider: TranscriptionProvider;
  display_hint: string | null;
  model_id: string | null;
  is_active: boolean;
  validation_status: TranscriptionValidationStatus | null;
  last_validated_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface TranscriptionProviderInfo {
  id: TranscriptionProvider;
  name: string;
  description: string;
  configured: boolean;
  validation_status: TranscriptionValidationStatus | null;
  model_id: string | null;
  display_hint: string | null;
}

export interface TranscriptionConfigCreateRequest {
  provider: TranscriptionProvider;
  api_key: string;
  model_id?: string;
  validate?: boolean;
}

export interface TranscriptionConfigValidateRequest {
  provider: TranscriptionProvider;
  api_key: string;
  model_id?: string;
}

export interface TranscriptionConfigValidateResponse {
  provider: string;
  valid: boolean;
  message: string;
}

export interface TranscriptionConfigListResponse {
  items: TranscriptionConfig[];
}

export interface TranscriptionProvidersListResponse {
  providers: TranscriptionProviderInfo[];
}

export interface TranscriptionModelListRequest {
  provider: TranscriptionProvider;
  api_key: string;
}

export interface TranscriptionModelListResponse {
  provider: string;
  models: string[];
}

// AI Feature Configuration Types

export type AIFeature = 'resume_extraction' | 'playbook_agent';

export interface ModelInfo {
  id: string;
  name: string;
  max_tokens: number | null;
  input_cost_per_token: number | null;
  output_cost_per_token: number | null;
}

export interface ProviderModels {
  provider: LLMProvider;
  provider_name: string;
  models: ModelInfo[];
}

export interface AvailableModelsResponse {
  providers: ProviderModels[];
  has_validated_keys: boolean;
}

export interface AIFeatureConfigRead {
  id: string;
  feature: string;
  provider: string;
  model_id: string;
  model_name: string | null;
  temperature: number | null;
  max_tokens: number | null;
  created_at: string;
  updated_at: string | null;
}

export interface AIFeatureInfo {
  feature: string;
  display_name: string;
  description: string;
  config: AIFeatureConfigRead | null;
  is_default: boolean;
  default_model: string;
}

export interface AIFeatureListResponse {
  features: AIFeatureInfo[];
  default_model: string;
}

export interface AIFeatureConfigCreate {
  provider: string;
  model_id: string;
  temperature?: number;
  max_tokens?: number;
}

// Entity Type Definition Types (Configuration-Driven Architecture)

export interface EntityTypeFeatures {
  has_lifecycle: boolean;
  has_projection: boolean;
  has_form: boolean;
}

export interface FieldDefinition {
  name: string;
  type: string;
  required?: boolean;
  format?: string;
  items?: string;
  description?: string;
}

export interface EntityTypeSchema {
  fields: FieldDefinition[];
}

export interface IdentifierConfig {
  identifier_label?: string | null;
  identifier_template?: string | null;
  /** Custom "required" message shown under the identifier input when left blank. */
  identifier_error_message?: string | null;
}

export type EntityTypeSchemaDefinition = IdentifierConfig & {
  fields?: FieldDefinition[];
} & Record<string, unknown>;

export interface RelationDefinition {
  target_type: string;
  relation_name: string;
  cardinality: 'one_to_one' | 'one_to_many' | 'many_to_one' | 'many_to_many';
}

export interface EntityType {
  id: string;
  entity_type_id?: string;
  organization_id: string;
  name: string;
  display_name: string | null;
  description: string | null;
  schema: EntityTypeSchema | null;
  schema_definition?: EntityTypeSchemaDefinition;
  version?: number;
  allowed_relations: RelationDefinition[] | null;
  default_state_machine_id: string | null;
  features: EntityTypeFeatures | null;
  icon: string | null;
  color: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface EntityTypeSummary {
  id: string;
  name: string;
  display_name: string | null;
  icon: string | null;
  color: string | null;
  features: EntityTypeFeatures | null;
}

export interface EntityTypeListResponse {
  items: EntityType[];
  total: number;
}

export interface EntityTypeRelationItem {
  relation_def_id: string;
  from_entity_type_id: string;
  to_entity_type_id: string;
  relation_name: string | null;
  relation_type: string;
}

// One field an entity type inherits from a related entity (declaration target).
// Merged into entity data at read time, so a connector can use it as `$entity.<field>`.
export interface EntityTypeInheritedFieldItem {
  field: string;
  source_entity_type_id: string;
  relation_type: string; // 'SNAPSHOT' | 'REFERENCE'
}

// Response for GET /entity-types/{id}/relations — outgoing relations plus the
// fields this type inherits from parents (auto `<parent>_id` + mapped fields).
export interface EntityTypeRelationListResponse {
  organization_id: string;
  items: EntityTypeRelationItem[];
  inherited_fields: EntityTypeInheritedFieldItem[];
}

export interface EntityTypeCreateRequest {
  name: string;
  display_name?: string;
  description?: string;
  schema?: EntityTypeSchema;
  schema_definition?: EntityTypeSchemaDefinition;
  allowed_relations?: RelationDefinition[];
  default_state_machine_id?: string;
  features?: EntityTypeFeatures;
  icon?: string;
  color?: string;
}

export interface EntityTypeUpdateRequest {
  display_name?: string;
  description?: string;
  schema?: EntityTypeSchema;
  schema_definition?: EntityTypeSchemaDefinition;
  allowed_relations?: RelationDefinition[];
  default_state_machine_id?: string;
  features?: EntityTypeFeatures;
  icon?: string;
  color?: string;
}

// Document Type Configuration Types (Configuration-Driven Architecture)

// Upload context - where a document type can be uploaded
export interface UploadContextConfig {
  entity_type: string;  // e.g., "ATS.Candidate", "ATS.Application"
  label?: string;
  states?: string[];  // Optional state filter for lifecycle entities
}

// Validation rule for extracted data
export interface ValidationRule {
  field: string;
  rule: string;  // "required", "email", "phone", "regex", "min_length", "max_length", "one_of"
  params?: Record<string, unknown>;
}

// Post-processing action configuration
export interface PostAction {
  type: string;  // "create_entity", "update_entity", "find_or_create", "link_entity", "run_playbook"
  entity_type?: string;
  field_mapping?: Record<string, string>;
  playbook_id?: string;
  trigger_data?: Record<string, unknown>;
  condition?: string;
}

// Document agent pipeline configuration
export interface DocumentAgentConfig {
  stages: string[];  // ["EXTRACT", "VALIDATE", "ACTION"]
  validation_rules?: ValidationRule[];
  post_actions?: PostAction[];
}

export interface DocumentType {
  id: string;
  type_id: string;
  display_name: string;
  description: string | null;
  folder: string;
  allowed_extensions: string[];
  max_size_mb: number;
  // AI extraction settings (legacy)
  extract_enabled: boolean;
  system_prompt: string | null;
  extraction_prompt: string | null;
  extraction_schema: Record<string, unknown> | null;
  // Agent-based processing (preferred)
  agent_enabled: boolean;
  agent_system_prompt: string | null;  // Agent system message (instructions)
  agent_prompt: string | null;  // Agent user prompt (task to perform)
  agent_tools: string[] | null;  // List of enabled tool names
  agent_model: string | null;  // LiteLLM model ID
  // Entity settings
  is_entity: boolean;
  entity_type_name: string | null;
  state_machine_name: string | null;
  // Upload contexts and agent config
  upload_contexts: UploadContextConfig[] | null;
  agent_config: DocumentAgentConfig | null;
  // Status
  is_active: boolean;
  is_system: boolean;  // System types cannot be deleted
  is_preview_thumbnail: boolean;
  metadata?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string | null;
}

export interface DocumentTypeListResponse {
  items: DocumentType[];
  total: number;
}

export interface DocumentTypeCreateRequest {
  type_id: string;
  display_name: string;
  description?: string;
  folder: string;
  allowed_extensions: string[];
  max_size_mb?: number;
  // AI extraction (legacy)
  extract_enabled?: boolean;
  system_prompt?: string;
  extraction_prompt?: string;
  extraction_schema?: Record<string, unknown>;
  // Agent-based processing (preferred)
  agent_enabled?: boolean;
  agent_system_prompt?: string;  // Agent system message (instructions)
  agent_prompt?: string;  // Agent user prompt (task to perform)
  agent_tools?: string[];  // List of enabled tool names
  agent_model?: string;  // LiteLLM model ID
  // Entity settings
  is_entity?: boolean;
  entity_type_name?: string;
  state_machine_name?: string;
  // Upload contexts and agent config
  upload_contexts?: UploadContextConfig[];
  agent_config?: DocumentAgentConfig;
  is_active?: boolean;
  metadata?: Record<string, unknown>;
}

export interface DocumentTypeUpdateRequest {
  display_name?: string;
  description?: string;
  folder?: string;
  allowed_extensions?: string[];
  max_size_mb?: number;
  // AI extraction (legacy)
  extract_enabled?: boolean;
  system_prompt?: string;
  extraction_prompt?: string;
  extraction_schema?: Record<string, unknown>;
  // Agent-based processing (preferred)
  agent_enabled?: boolean;
  agent_system_prompt?: string;  // Agent system message (instructions)
  agent_prompt?: string;  // Agent user prompt (task to perform)
  agent_tools?: string[];  // List of enabled tool names
  agent_model?: string;  // LiteLLM model ID
  // Entity settings
  is_entity?: boolean;
  entity_type_name?: string;
  state_machine_name?: string;
  // Upload contexts and agent config
  upload_contexts?: UploadContextConfig[];
  agent_config?: DocumentAgentConfig;
  is_active?: boolean;
  is_preview_thumbnail?: boolean;
  metadata?: Record<string, unknown>;
}

// Document Agent Tool Manifest Types

export type DocumentToolCategory = 'document' | 'entity' | 'workflow' | 'communication' | 'integration';

export interface DocumentAgentTool {
  name: string;
  display_name: string;
  description: string;
  category: DocumentToolCategory;
  risk_level: 'low' | 'medium' | 'high';
  default_enabled: boolean;
}

export interface ToolManifestResponse {
  tools: DocumentAgentTool[];
  default_tools: string[];
}

export interface DocumentToolPreset {
  name: string;
  description: string;
  tools: string[];
}

export type ToolPresetsResponse = Record<string, DocumentToolPreset>;

// Document Metadata Types (stored in entity.data.documents[])

export interface DocumentMetadata {
  id: string;
  type: string;  // document type_id (e.g., "resume", "email_thread")
  filename: string;
  storage_key: string;
  content_type: string;
  size_bytes: number;
  uploaded_at: string;
  uploaded_by: string;
  status?: string;  // UPLOADED | PROCESSING | PROCESSED | FAILED
  failure_reason?: string | null;
  metadata?: Record<string, unknown>;
  extracted_data?: Record<string, unknown>;
  action_results?: DocumentActionResults;
  /** External review-only source. Preview/download uses this URL directly; it
   * is not a managed platform file until bulk-import confirmation. */
  source_url?: string;
}

// Results from post-action execution
export interface DocumentActionResults {
  success: boolean;
  actions_completed: number;
  actions_failed: number;
  created_entity_ids?: string[];
  triggered_playbook_run_id?: string;
  error?: string;
}

export interface DocumentUploadResponse {
  document_id: string;
  filename: string;
  storage_key: string;
  content_type: string;
  size_bytes: number;
  entity_id: string;
  document_type: string;
  auto_deduplicated?: boolean;
  extracted_data?: Record<string, unknown>;
  action_results?: DocumentActionResults;
}

export interface DocumentListResponse {
  items: DocumentMetadata[];
  total: number;
}

export interface DocumentDeleteResponse {
  success: boolean;
  document_id: string;
  message: string;
}

// Transcription Types

export type TranscriptionCaptureMode = 'bot' | 'local';
export type TranscriptionMeetingPlatform = 'google_meet' | 'microsoft_teams';
export type TranscriptionStatus = 'queued' | 'joining' | 'recording' | 'processing' | 'completed' | 'failed';

export interface TranscriptionSession {
  id: string;
  entity_type: string;
  entity_id: string;
  meeting_url?: string | null;
  capture_mode: TranscriptionCaptureMode;
  meeting_platform?: TranscriptionMeetingPlatform | null;
  status: TranscriptionStatus;
  started_at?: string | null;
  ended_at?: string | null;
  transcript_document_id?: string | null;
  created_by?: string | null;
  created_at: string;
}

export interface TranscriptionSessionCreateRequest {
  entity_type: string;
  entity_id: string;
  meeting_url?: string | null;
  capture_mode: TranscriptionCaptureMode;
  meeting_platform?: TranscriptionMeetingPlatform | null;
}

export interface TranscriptionSessionCreateResponse {
  session: TranscriptionSession;
  participant_token?: string | null;
}

export interface TranscriptionSessionListResponse {
  items: TranscriptionSession[];
  total: number;
}

export interface TranscriptionFinalizeResponse {
  success: boolean;
  message: string;
  transcript_document_id?: string | null;
}

// Background Job Types

export type JobStatus = 'queued' | 'processing' | 'completed' | 'failed';

export interface JobProgress {
  completed: number;
  failed: number;
  total: number;
}

export interface BackgroundJob {
  id: string;
  job_type: string;
  status: JobStatus;
  execution_mode?: 'agent' | 'llm';
  agent_name?: string | null;
  agent_definition_id?: string | null;
  filename?: string | null;
  progress: JobProgress;
  error_message?: string;
  created_at: string;
  updated_at?: string;
  completed_at?: string;
}

export interface JobListResponse {
  items: BackgroundJob[];
  total: number;
}

// Document Processing Job Types

export type ProcessingJobStatus = 'PENDING' | 'EXTRACTING' | 'VALIDATING' | 'ACTIONING' | 'COMPLETED' | 'FAILED';

export interface DocumentProcessingJob {
  id: string;
  document_id: string;
  storage_key: string;
  filename: string;
  doc_type_id: string;
  source_entity_id: string | null;
  source_entity_type: string | null;
  upload_context: string | null;
  status: ProcessingJobStatus;
  current_stage: string | null;
  progress_pct: number;
  extraction_result: Record<string, unknown> | null;
  validation_result: Record<string, unknown> | null;
  action_results: Record<string, unknown> | null;
  created_entity_ids: string[] | null;
  triggered_playbook_run_id: string | null;
  error_message: string | null;
  error_stage: string | null;
  retry_count: number;
  created_by: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface DocumentProcessingJobListResponse {
  items: DocumentProcessingJob[];
  total: number;
}

// User Management Types

export type UserRole = 'superadmin' | 'admin' | 'recruiter' | 'hiring_manager' | 'viewer';
export type UserStatus = 'pending' | 'active' | 'suspended' | 'rejected';
export type AuthType = 'local' | 'google' | 'microsoft';

export interface User {
  id: string;
  email: string;
  full_name: string;
  avatar_url: string | null;
  role: UserRole;
  status: UserStatus;
  auth_type: AuthType;
  is_active: boolean;
  organization_id: string | null;
  last_login_at: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface UserListResponse {
  items: User[];
}

export interface UserRoleUpdateRequest {
  role: UserRole;
}

export interface UserStatsResponse {
  total: number;
  by_status: Record<UserStatus, number>;
  by_role: Record<UserRole, number>;
}

// Invitation Types

export type InvitationStatus = 'pending' | 'accepted' | 'expired' | 'revoked';

export interface Invitation {
  id: string;
  organization_id: string;
  email: string;
  role: string;
  status: InvitationStatus;
  invited_by_user_id: string | null;
  expires_at: string;
  accepted_at: string | null;
  created_at: string;
}

export interface InvitationCreate {
  email: string;
  role: string;
}

export interface InvitationValidation {
  valid: boolean;
  error?: string;
  email?: string;
  role?: string;
  organization_name?: string;
  expires_at?: string;
  user_exists?: boolean;
}

export interface InvitationAccept {
  token: string;
  full_name?: string;
  password?: string;
}

export interface InvitationAcceptResponse {
  message: string;
  user_id: string;
  already_member: boolean;
}

// Organization Management Types

export type OrganizationStatus = 'pending' | 'active' | 'suspended' | 'archived' | 'rejected';

export interface Organization {
  id: string;
  name: string;
  slug: string;
  domain: string | null;
  settings: Record<string, unknown>;
  status: OrganizationStatus;
  logo_url: string | null;
  requested_by_user_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface OrganizationWithRequester extends Organization {
  requester_email: string | null;
  requester_name: string | null;
}

export interface PendingOrganizationListResponse {
  items: OrganizationWithRequester[];
  total: number;
}

export interface OrganizationListResponse {
  items: Organization[];
  total: number;
}

// ============================================================================
// Agent Definition Types
// ============================================================================

export interface AgentSuggestion {
  label: string;
  prompt: string;
}

export interface AgentConstraints {
  max_iterations: number;
  require_approval: string[];
  // Not editable in the agent editor, but must round-trip: the backend replaces
  // `constraints` wholesale on update, so omitting a stored key silently wipes
  // it (e.g. bulk_import_extractor's `temperature: 0`).
  temperature?: number | null;
}

export interface AgentDefinition {
  definition_id: string;
  name: string;
  display_name: string;
  description: string | null;
  system_prompt: string;
  allowed_tools: string[] | null;
  constraints: AgentConstraints;
  suggestions: AgentSuggestion[];
  model_override: string | null;
  is_active: boolean;
  is_system: boolean;
  organization_id: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface AgentDefinitionListItem {
  definition_id: string;
  name: string;
  display_name: string;
  description: string | null;
  is_active: boolean;
  is_system: boolean;
  tool_count: number;
  approval_count: number;
  suggestion_count: number;
}

export interface AgentDefinitionCreateRequest {
  name: string;
  display_name: string;
  description?: string;
  system_prompt: string;
  allowed_tools?: string[] | null;
  constraints?: AgentConstraints;
  suggestions?: AgentSuggestion[];
  model_override?: string;
  is_active?: boolean;
}

export interface AgentDefinitionUpdateRequest {
  display_name?: string;
  description?: string;
  system_prompt?: string;
  allowed_tools?: string[] | null;
  constraints?: AgentConstraints;
  suggestions?: AgentSuggestion[];
  model_override?: string;
  is_active?: boolean;
}

// Agent Run Types (phase-1 runtime)

export interface AgentRunCreateRequest {
  definition_id: string;
  input: string;
  session_id?: string;
  context?: Record<string, unknown>;
}

export interface AgentRun {
  run_id: string;
  definition_id: string;
  session_id: string | null;
  status: string;
  input: string;
  output: string | null;
  error: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  updated_at: string | null;
}

export interface AgentRunListResponse {
  items: AgentRun[];
  total: number;
}

// Agent Chat Types

export interface PinnedEntity {
  id: string;
  type: string;
  label: string;
}

export interface AgentChatRequest {
  agent: string;
  message: string;
  session_id?: string;
  context?: {
    pinned_entities?: PinnedEntity[];
    [key: string]: unknown;
  };
}

export interface AgentTraceEvent {
  id: string;
  seq: number;
  kind: string;
  payload: Record<string, unknown> | null;
  created_at: string;
}

export interface AgentTraceRunListItem {
  id: string;
  agent_name: string;
  run_type: string;
  status: string;
  model: string | null;
  input_message: string | null;
  session_id: string | null;
  message_id: string | null;
  user_id: string | null;
  error: string | null;
  tokens_used: number;
  iterations: number | null;
  duration_ms: number | null;
  started_at: string;
  completed_at: string | null;
}

export interface AgentTraceRunDetail extends AgentTraceRunListItem {
  context: Record<string, unknown> | null;
  events: AgentTraceEvent[];
}

export interface AgentTraceRunListResponse {
  items: AgentTraceRunListItem[];
  total: number;
}

export interface AgentTraceSessionListItem {
  session_id: string;
  agent_name: string;
  latest_run_id: string;
  latest_message_id: string | null;
  latest_status: string;
  latest_input_message: string | null;
  user_id: string | null;
  model: string | null;
  run_count: number;
  total_tokens: number;
  total_duration_ms: number;
  first_started_at: string;
  last_started_at: string;
  last_completed_at: string | null;
}

export interface AgentTraceSessionListResponse {
  items: AgentTraceSessionListItem[];
  total: number;
}

export interface ToolCallInfo {
  tool: string;
  args: Record<string, unknown>;
  result?: Record<string, unknown>;
  success: boolean;
  duration_ms: number;
}

export interface PendingAction {
  action_id: string;
  tool: string;
  args: Record<string, unknown>;
  description: string;
  status: 'pending' | 'approved' | 'rejected';
}

export interface AgentChatResponse {
  success: boolean;
  session_id: string;
  message_id: string;
  content: string;
  tool_calls: ToolCallInfo[];
  pending_actions: PendingAction[];
  tokens_used: number;
  error?: string;
}

export interface AgentSession {
  session_id: string;
  definition_id: string | null;
  agent_name: string | null;
  title: string | null;
  context: Record<string, unknown> | null;
  message_count: number;
  total_tokens: number;
  created_at: string;
  updated_at: string;
}

export interface AgentMessage {
  message_id: string;
  role: 'user' | 'agent';
  content: string;
  tool_calls: ToolCallInfo[] | null;
  pending_actions: PendingAction[] | null;
  tokens_used: number;
  created_at: string;
}

export interface AgentSessionWithMessages {
  session: AgentSession;
  messages: AgentMessage[];
}

export interface AgentToolInfo {
  id?: string;
  name: string;
  display_name?: string;
  description: string;
  category?: string;
  is_mutating?: boolean;
  requires_approval?: boolean;
  is_enabled?: boolean;
  package_enabled?: boolean;
  parameters: Record<string, unknown>;
}

export interface AgentToolManifestResponse {
  tools: AgentToolInfo[];
}

export interface McpServerPackage {
  id: string;
  server_key: string;
  name: string;
  description: string | null;
  version: string;
  is_platform_managed: boolean;
  is_active: boolean;
  is_enabled: boolean;
  config: Record<string, unknown>;
}

export interface McpCapability {
  id: string;
  server_package_id: string;
  capability_key: string;
  tool_id: string;
  display_name: string;
  description: string;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown> | null;
  category: string;
  is_mutating: boolean;
  requires_approval: boolean;
  package_enabled: boolean;
  is_enabled: boolean;
  is_active: boolean;
}

export interface McpToolingOverview {
  packages: McpServerPackage[];
  capabilities: McpCapability[];
}

// ============================================================================
// Integration Types (Google Calendar, etc.)
// ============================================================================

export type IntegrationProvider = 'google_calendar';

export type IntegrationStatus = 'pending' | 'connected' | 'expired' | 'revoked';

export interface UserIntegration {
  id: string;
  user_id: string;
  organization_id: string;
  provider: IntegrationProvider;
  provider_email: string | null;
  status: IntegrationStatus;
  scopes: string[] | null;
  connected_at: string | null;
  last_used_at: string | null;
  last_error: string | null;
  last_error_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface IntegrationListResponse {
  integrations: UserIntegration[];
}

export interface GoogleCalendarAuthUrl {
  auth_url: string;
  state: string;
}

export interface GoogleCalendarCallbackRequest {
  code: string;
  state: string;
}

export interface IntegrationConnectResponse {
  success: boolean;
  message: string;
  integration: UserIntegration | null;
}

// ============================================================================
// Scheduling Types
// ============================================================================

export interface ScheduleInterviewRequest {
  date: string; // YYYY-MM-DD
  start_time: string; // HH:MM (24-hour)
  duration_minutes: number;
  title?: string;
  description?: string;
  location?: string;
  additional_attendees?: string[];
  timezone: string;
  send_invites: boolean;
}

export interface ScheduleInterviewResponse {
  success: boolean;
  message: string;
  method: 'google_calendar' | 'ics_email';
  event_id: string | null;
  html_link: string | null;
  scheduled_at: string;
  attendees: string[];
  title: string;
}

// ============================================================================
// Upload Job Types (for presigned URL uploads)
// ============================================================================

export type UploadFileStatus = 'pending' | 'uploading' | 'completed' | 'failed';

export interface UploadFileProgress {
  file_id: string;
  filename: string;
  size_bytes: number;
  uploaded_bytes: number;
  status: UploadFileStatus;
  storage_key: string;
  error?: string;
}

export interface UploadJob {
  id: string;
  session_id: string;
  status: 'preparing' | 'uploading' | 'completing' | 'completed' | 'failed';
  files: UploadFileProgress[];
  storage_type: 'minio' | 'local';
  extraction_job_id?: string; // Linked extraction job after upload completes
  error?: string;
  created_at: string;
}

// API types for presigned upload
export interface PrepareUploadFileRequest {
  filename: string;
  size_bytes: number;
  content_type: string;
}

export interface PrepareUploadRequest {
  files: PrepareUploadFileRequest[];
}

export interface PrepareUploadFileResponse {
  file_id: string;
  filename: string;
  storage_key: string;
  presigned_url: string | null;
  expires_at: string | null;
}

export interface RejectedFileResponse {
  filename: string;
  reason: string;
}

export interface PrepareUploadResponse {
  upload_session_id: string;
  storage_type: 'minio' | 'local';
  files: PrepareUploadFileResponse[];
  rejected_files: RejectedFileResponse[];
  fallback_upload_url: string | null;
}

export interface UploadedFileInfo {
  file_id: string;
  filename: string;
  storage_key: string;
}

export interface CompleteUploadRequest {
  upload_session_id: string;
  uploaded_files: UploadedFileInfo[];
}

export interface CompleteUploadResponse {
  job_id: string;
  status: string;
  total_files: number;
  message: string;
}

export interface PublicFormSchemaResponse {
  token: string;
  run_id: string;
  organization_id: string;
  entity_id: string;
  status: string;
  form: {
    schema_key: string;
    name: string;
    description?: string | null;
    entity_type: string;
    fields: Array<Record<string, unknown>>;
  };
}

export interface PublicFormSubmitRequest {
  token: string;
  fields: Record<string, unknown>;
}

export interface PublicFormSubmitResponse {
  success: boolean;
  run_id: string;
  entity_id: string;
}

// ============================================================================
// Activity Timeline Types
// ============================================================================

/**
 * One row from GET /audit-events — the single unified audit log endpoint.
 *
 * Replaces the old, entity-specific EntityEventResponse and the old
 * transition-specific ActivityRecord (both are gone — their endpoints,
 * GET /entity-records/{id}/events and GET /entities/{id}/transitions/history,
 * no longer exist). `metadata`'s shape depends on `event_type` — see
 * GET /audit-events/constants for the full catalog, and the root-level
 * `audit_events_api_guide.md` for the per-event-type field reference.
 */
export interface AuditEventResponse {
  id: string;
  organization_id: string;
  metadata_type: string;
  entity_type: string | null;
  entity_id: string | null;
  /** Human-readable identifier of the record, null when it no longer exists. */
  entity_identifier: string | null;
  /** Archived records have no detail page to open. */
  entity_archived: boolean;
  user_id: string | null;
  event_type: string;
  actor_type: string;
  actor_id: string | null;
  actor_name: string | null;
  actor_role: string | null;
  correlation_id: string | null;
  source: string | null;
  before_state: string | null;
  after_state: string | null;
  metadata: Record<string, unknown>;
  event_timestamp: string | null;
}

/** Paginated response from GET /audit-events. */
export interface AuditEventListResponse {
  items: AuditEventResponse[];
  total: number;
  entity_id: string | null;
}

// ── Connectors ────────────────────────────────────────────────────────────────

export interface Connector {
  id: string;
  organization_id: string;
  name: string;
  entity_types: string[];
  base_url: string;
  method: string;
  path: string;
  headers: Record<string, string>;
  query_params: Record<string, string>;
  content_type: string;
  /** Object, or an array for batch endpoints that take a list of objects. */
  body_template: Record<string, unknown> | unknown[] | string | null;
  auth_type: string;
  auth_config: Record<string, unknown>;
  secret_hints: Record<string, string>;
  response_mapping: Record<string, string>;
  success_when: Record<string, unknown>;
  expose_as_tool: boolean;
  status: string;
  validation_status: string | null;
  last_validated_at: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConnectorCreateRequest {
  name: string;
  entity_types?: string[];
  base_url: string;
  method?: string;
  path?: string;
  headers?: Record<string, string>;
  query_params?: Record<string, string>;
  content_type?: string;
  body_template?: Record<string, unknown> | unknown[] | string | null;
  auth_type?: string;
  auth_config?: Record<string, unknown>;
  secrets?: Record<string, string>;
  response_mapping?: Record<string, string>;
  success_when?: Record<string, unknown>;
  expose_as_tool?: boolean;
}

export interface ConnectorUpdateRequest extends Partial<ConnectorCreateRequest> {}

export interface ConnectorListResponse {
  items: Connector[];
  total: number;
}

export interface ConnectorTestResponse {
  success: boolean;
  status_code: number | null;
  message: string;
  response_json: Record<string, unknown> | null;
}

// ── Remote MCP servers ───────────────────────────────────────────────────────
// Pre-built catalog entries in Settings → Connectors (Apps strip), backed by
// /api/remote-mcp. See docs/remote_mcp_frontend_handoff.MD.

/** Server-reported lifecycle state (matches the backend's RemoteMcpServerStatus). */
export type RemoteMcpServerStatus = 'configured' | 'connected' | 'needs_reauth' | 'error';

/** Tile-facing status: same as the server status, plus a frontend-only transient while a request is in flight. */
export type RemoteMcpTileStatus = RemoteMcpServerStatus | 'connecting';

export interface RemoteMcpAppDefinition {
  /**
   * The backend's preset key (e.g. "github"). Sent as `preset` on create, and
   * echoed back in a created server's `auth_config.preset` — which is how an
   * existing connection is matched back to its catalog entry.
   */
  id: string;
  name: string;
  description: string;
  icon: ComponentType<{ className?: string }>;
  // ^ any component shaped like a lucide icon or a local brand-mark SVG works here.
}

export interface RemoteMcpServer {
  id: string;
  name: string;
  server_url: string;
  auth_type: string;
  status: RemoteMcpServerStatus;
  is_enabled: boolean;
  requires_authorization: boolean;
  tool_count: number;
  secret_hints: Record<string, string>;
  token_expires_at: string | null;
  last_error: string | null;
  last_discovered_at: string | null;
  auth_config: Record<string, unknown>;
}

export interface RemoteMcpServerListResponse {
  items: RemoteMcpServer[];
  total: number;
}

export interface RemoteMcpServerCreateRequest {
  name: string;
  server_url?: string;
  auth_type?: string;
  is_enabled?: boolean;
  /** A known catalog entry (e.g. "github") — fills every other field server-side. */
  preset?: string;
  api_key?: string;
  api_key_location?: string;
  api_key_name?: string;
  client_id?: string;
  client_secret?: string;
  authorize_url?: string;
  token_url?: string;
  scopes?: string[];
}

export interface RemoteMcpServerUpdateRequest extends Partial<RemoteMcpServerCreateRequest> {}

export interface RemoteMcpTool {
  id: string;
  tool_name: string;
  display_name: string;
  description: string;
  input_schema: Record<string, unknown>;
  is_active: boolean;
}

export interface RemoteMcpDiscoverResponse {
  server_id: string;
  ok: boolean;
  status: RemoteMcpServerStatus;
  tool_count: number;
  tools: RemoteMcpTool[];
  server_name: string;
  server_version: string;
  error: string | null;
}

export interface RemoteMcpAuthorizeResponse {
  authorization_url: string;
  state: string;
}

export interface RemoteMcpOAuthCallbackResponse {
  connected: boolean;
  status: RemoteMcpServerStatus;
  token_expires_at: string | null;
}
