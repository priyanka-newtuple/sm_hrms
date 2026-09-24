import type { AvailableTransition } from '@/core/types';

export interface DemoEntityCard {
  id: string;
  enrollmentId?: string;
  workflowId?: string;
  title: string;
  subtitle: string;
  stateId: string;
  stateEnteredAt?: string;
  slaDueAt?: string;
  dueDate?: string;
  thumbnailUrl?: string;
  /** Resolved display name of the assigned user, when assigned. */
  assigneeName?: string;
  /**
   * Raw entity data bag forwarded from WorkflowEntityState.data.
   * Skin-provided kanban card components use this to render domain-specific
   * metadata fields (e.g. incident number, store name, priority).
   */
  data?: Record<string, unknown>;
}

export interface DemoSchemaField {
  field: string;
  description?: string;
  enum_values?: string[];
}

export interface DemoState {
  name: string;
  description?: string;
  order?: number;
  tags?: string[];
}

export interface DemoTransition {
  key: string;
  trigger: string;
  label?: string;
  from: string;
  to_state: string;
  description?: string;
  allowed_roles?: unknown[] | null;
  required_fields?: unknown[] | null;
  guards?: unknown[] | null;
  pre_transition_tasks?: unknown[] | null;
  post_transition_tasks?: unknown[] | null;
}

export interface DemoPipelineFile {
  machine_name: string;
  base_version: number;
  definition: {
    machine_key: string;
    name: string;
    description?: string;
    entity_type: string;
    initial_state: string;
    states: DemoState[];
    transitions: DemoTransition[];
    entity_schema?: {
      fields?: DemoSchemaField[];
    };
  };
}

export interface StateAccent {
  dot: string;
  badge: string;
  card: string;
  soft: string;
  text: string;
  border: string;
}

export interface PipelineTransitionEdge {
  id: string;
  sourceId: string;
  targetId: string;
  sourceLabel: string;
  targetLabel: string;
  label: string;
  trigger: string;
  description: string;
  guards: string[];
  requiredFields: string[];
  allowedRoles: string[];
  preTasks: string[];
  postTasks: string[];
}

export interface PipelineStateNode {
  id: string;
  name: string;
  label: string;
  description: string;
  tags: string[];
  order: number;
  flowRank: number;
  isInitial: boolean;
  isTerminal: boolean;
  kind: 'initial' | 'active' | 'terminal';
  accent: StateAccent;
  incomingTransitionIds: string[];
  outgoingTransitionIds: string[];
  incomingCount: number;
  outgoingCount: number;
}

export interface PipelineFlowNodeData {
  state: PipelineStateNode;
}

export interface PipelineSchemaField {
  field: string;
  label: string;
  enum_values?: string[];
  enum_labels?: string[];
}

export interface PipelineListEntity {
  entity_id: string;
  state_id?: string;
  workflow_id?: string;
  current_state: string;
  /** Prose description of the current state, when the workflow defines one. */
  current_state_description?: string;
  created_at: string;
  updated_at: string;
  data: Record<string, unknown>;
  /** First-class entity due date, independent of schema fields and workflow SLA. */
  due_date?: string;
  /** Aggregated cross-workflow views only: workflow display name. */
  machine_name?: string;
  /** Aggregated cross-workflow views only: resolved owner display name. */
  owner_name?: string;
  /** Aggregated cross-workflow views only: entity type name. */
  entity_type?: string;
  /** Assigned user id, when assigned. */
  assignee_id?: string;
  /** Resolved display name of the assigned user, when assigned. */
  assignee_name?: string;
  /** Page-batched transition previews; avoids one availability request per row. */
  transition_options?: AvailableTransition[];
}

export interface PipelineViewModel {
  machineName: string;
  machineVersion: number;
  entityType: string;
  machineDescription: string;
  states: PipelineStateNode[];
  terminalStates: PipelineStateNode[];
  transitions: PipelineTransitionEdge[];
  schemaFields: PipelineSchemaField[];
  stateById: Map<string, PipelineStateNode>;
  transitionById: Map<string, PipelineTransitionEdge>;
}
