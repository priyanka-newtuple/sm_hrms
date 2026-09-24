import type { FieldExtension, TableFieldConfig } from '@/core/types';
import type { CalcNode } from '@/shared/utils/calc';

export const PLACEHOLDER_ENTITY_TYPE = 'entity';

export type FieldType =
  | "string"
  | "email"
  | "phone"
  | "url"
  | "int"
  | "float"
  | "boolean"
  | "date"
  | "datetime"
  | "enum"
  | "multi_select"
  | "auto_number"
  | "currency"
  | "timer_duration"
  | "text"
  | "json"
  // Mapped from a form schema's document field so publishing doesn't record it
  // as a string and report permanent schema drift. Deliberately absent from
  // FIELD_TYPES below: a document field needs a file type chosen for it, and
  // the funnel builder has no UI for that, so it isn't hand-pickable here.
  | "document";

export const FIELD_TYPES: FieldType[] = [
  "string",
  "email",
  "text",
  "int",
  "float",
  "boolean",
  "datetime",
  "enum",
  "json",
];

export interface EntityField {
  field: string;
  type: FieldType;
  required: boolean;
  nullable: boolean;
  default: unknown;
  enum_values: string[];
  picklist_id: string | null;
  /** The second picklist of a "Picklist Multi (Dropdown Add)" field, and the
   *  Field Library fields each of its options reveals. The engine stores such a
   *  field as `multi_select`, so these are the discriminator for it. */
  picklist_id_2?: string | null;
  enum_values_2?: string[];
  enum_labels_2?: string[];
  extensions?: Record<string, FieldExtension> | null;
  /** Names what those extension fields collect; drives the form's badges. */
  extension_label?: string | null;
  /** The wizard's editable copy; see `core/types/wizardCopy`. */
  step1_label?: string | null;
  step1_description?: string | null;
  step2_label?: string | null;
  step2_description?: string | null;
  step3_label?: string | null;
  step3_description?: string | null;
  description: string;
  placeholder?: string | null;
  editable?: boolean | null;
  col_span?: "full" | "half" | null;
  auto_number_config?: { affix_mode?: "none" | "prefix" | "suffix"; affix?: string } | null;
  currency_config?: { currency_code?: string } | null;
  document_config?: { type_id?: string; multiple?: boolean } | null;
  table_config?: TableFieldConfig | null;
  calc?: CalcNode | null;
  /** Per-field colour overrides, and a value-level read-only lock that is
   *  independent of RBAC field permissions. Both apply to any field type. */
  style_config?: { background_color?: string; text_color?: string } | null;
  read_only?: boolean | null;
  /** States whose pinned Method contributed this field; empty = the workflow's
   *  own field, which belongs to every state. */
  source_states?: string[];
  /** `'inherited'` when a pinned Method block field resolves from a linked
   *  record instead of being entered on this one. Read-only on the record;
   *  the backend refuses writes to it and overlays the value at read time. */
  ownership?: "owned" | "inherited" | null;
  /** Where an `ownership: 'inherited'` field takes its value from. */
  source?: { context_entity_type: string; context_field: string } | null;
}

export interface EntitySchema {
  entity_type: string;
  fields: EntityField[];
}

export type StateTag = "initial" | "terminal" | string;

export interface StateAction {
  kind: string;
  config: Record<string, unknown>;
  outcome_triggers: Record<string, string>;
  failure_policy: Record<string, unknown>;
}

/** A Method Library method captured by a workflow state. A null version means
 * the method's latest version will be resolved when the workflow is published. */
export interface MethodRef {
  method_id: string;
  version_id: string | null;
}

/** Publish-time presentation snapshot for one Method pinned to one state. */
export interface ResolvedMethodSchema {
  method_id: string;
  method_name: string;
  version_id: string;
  version: number;
  state_name: string;
  state_order: number | null;
  method_order: number;
  fields: EntityField[];
}

export interface StateNode {
  name: string;
  description: string;
  tags: StateTag[];
  order: number | null;
  /** Ordered action chain, executed sequentially on state entry. */
  on_state_actions?: StateAction[];
  sla_seconds: number | null;
  method_refs?: MethodRef[];
}

export interface RequiredField {
  field: string;
  required: boolean;
  type: FieldType | null;
}

export type GuardType =
  | "field_present"
  | "field_exact_match"
  | "numerical_value_gte"
  | "numerical_value_lte"
  | "numerical_value_in_set"
  | "compare_dates"
  | "custom";

export const GUARD_LIBRARY: {
  type: GuardType;
  label: string;
  description: string;
  needsValue: boolean;
}[] = [
  {
    type: "field_present",
    label: "Field is present",
    description: "Require that a field has a value before transitioning.",
    needsValue: false,
  },
  {
    type: "field_exact_match",
    label: "Field equals value",
    description: "Field must exactly match a given value.",
    needsValue: true,
  },
  {
    type: "numerical_value_gte",
    label: "Number is at least",
    description: "Numeric field must be greater than or equal to a value.",
    needsValue: true,
  },
  {
    type: "numerical_value_lte",
    label: "Number is at most",
    description: "Numeric field must be less than or equal to a value.",
    needsValue: true,
  },
  {
    type: "numerical_value_in_set",
    label: "Number is one of",
    description: "Numeric field must be one of an allowed set.",
    needsValue: true,
  },
  {
    type: "compare_dates",
    label: "Compare two datetimes",
    description: "Compare two datetime fields (e.g. start before end).",
    needsValue: false,
  },
  {
    type: "custom",
    label: "Custom guard",
    description: "Advanced: provide raw type, value and config.",
    needsValue: true,
  },
];

export interface Guard {
  type: GuardType | string;
  field: string;
  value: unknown;
  message: string;
  config: Record<string, unknown>;
}

export type TaskFailureMode = "stop" | "continue";

export interface TransitionTask {
  task: string;
  label: string;
  order: number;
  required: boolean;
  on_failure: TaskFailureMode;
  config: Record<string, unknown>;
}

export interface AutoTransitionConfig {
  enabled?: boolean;
  delay_seconds?: number | null;
}

export interface Transition {
  key: string;
  trigger: string;
  label: string;
  from: string;
  to_state: string;
  required_fields: RequiredField[];
  guards: Guard[];
  pre_transition_tasks: TransitionTask[];
  post_transition_tasks: TransitionTask[];
  auto_transition: AutoTransitionConfig | null;
  description: string;
}

export interface StateMachineDefinition {
  machine_key: string;
  name: string;
  description: string;
  entity_type: string;
  // Optional grouping onto a WorkflowService, mirroring how a Method Block
  // carries category_id. A single value on the definition, not re-captured
  // per published version; never required to publish.
  service_id?: string | null;
  entity_schema: EntitySchema;
  states: StateNode[];
  /** Immutable Method boundaries captured when this workflow version was published. */
  method_schemas?: ResolvedMethodSchema[];
  initial_state: string;
  transitions: Transition[];
}

export interface StateMachineDocument {
  machine_name: string;
  base_version: number;
  definition: StateMachineDefinition;
}

export interface ValidationIssue {
  level: "error" | "warning";
  path: string;
  message: string;
  stateName?: string;
  transitionKey?: string;
  humanPath?: string;
  source?: "local" | "server";
}
