import type { StateMachineRecord } from '@/core/types';
import type {
  DemoPipelineFile,
  PipelineTransitionEdge,
  PipelineStateNode,
  PipelineViewModel,
  StateAccent,
} from '../types/pipeline';
import { humanize } from './labels';

/** @deprecated Use {@link humanize} from `shared/utils/labels`. Kept as a thin
 *  alias so existing view-model call sites read unchanged. */
const titleCase = humanize;


export function getStateAccent(stateName: string, kind: PipelineStateNode['kind']): StateAccent {
  const normalized = stateName.toLowerCase();

  if (kind === 'initial') {
    return {
      dot: 'bg-primary',
      badge: 'border-primary/20 bg-primary/10 text-primary',
      card: 'border-primary/20 bg-linear-to-br from-primary/8 via-card to-sky-500/10',
      soft: 'bg-primary/8',
      text: 'text-primary',
      border: 'border-primary/20',
    };
  }

  if (normalized.includes('approved')) {
    return {
      dot: 'bg-emerald-500',
      badge: 'border-emerald-200 bg-emerald-50 text-emerald-700',
      card: 'border-emerald-200 bg-linear-to-br from-emerald-50 via-card to-emerald-100/40',
      soft: 'bg-emerald-50',
      text: 'text-emerald-700',
      border: 'border-emerald-200',
    };
  }

  if (normalized.includes('reject')) {
    return {
      dot: 'bg-rose-500',
      badge: 'border-rose-200 bg-rose-50 text-rose-700',
      card: 'border-rose-200 bg-linear-to-br from-rose-50 via-card to-rose-100/40',
      soft: 'bg-rose-50',
      text: 'text-rose-700',
      border: 'border-rose-200',
    };
  }

  if (normalized.includes('cancel')) {
    return {
      dot: 'bg-amber-500',
      badge: 'border-amber-200 bg-amber-50 text-amber-700',
      card: 'border-amber-200 bg-linear-to-br from-amber-50 via-card to-amber-100/40',
      soft: 'bg-amber-50',
      text: 'text-amber-700',
      border: 'border-amber-200',
    };
  }

  if (normalized.includes('submit')) {
    return {
      dot: 'bg-sky-500',
      badge: 'border-sky-200 bg-sky-50 text-sky-700',
      card: 'border-sky-200 bg-linear-to-br from-sky-50 via-card to-sky-100/40',
      soft: 'bg-sky-50',
      text: 'text-sky-700',
      border: 'border-sky-200',
    };
  }

  return {
    dot: kind === 'terminal' ? 'bg-muted-foreground' : 'bg-violet-500',
    badge:
      kind === 'terminal'
        ? 'border-border bg-muted text-muted-foreground'
        : 'border-violet-200 bg-violet-50 text-violet-700',
    card:
      kind === 'terminal'
        ? 'border-border bg-linear-to-br from-muted via-card to-muted/70'
        : 'border-violet-200 bg-linear-to-br from-violet-50 via-card to-sky-50',
    soft: kind === 'terminal' ? 'bg-muted' : 'bg-violet-50',
    text: kind === 'terminal' ? 'text-muted-foreground' : 'text-violet-700',
    border: kind === 'terminal' ? 'border-border' : 'border-violet-200',
  };
}

function describeUnknown(
  value: unknown,
  fallbackPrefix: string,
  index: number,
  fieldLabelMap?: Map<string, string>,
): string {
  if (typeof value === 'string') return fieldLabelMap?.get(value) ?? titleCase(value);
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);

  if (value && typeof value === 'object') {
    const candidate = value as Record<string, unknown>;
    const preferredKeys = ['description', 'label', 'name', 'field', 'guard_type', 'type', 'kind'];

    for (const key of preferredKeys) {
      const entry = candidate[key];
      if (typeof entry === 'string' && entry.trim().length > 0) {
        return key === 'field' ? (fieldLabelMap?.get(entry) ?? titleCase(entry)) : titleCase(entry);
      }
    }
  }

  return `${fallbackPrefix} ${index + 1}`;
}

export function normalizeTextList(
  values: unknown[] | null | undefined,
  fallbackPrefix: string,
  fieldLabelMap?: Map<string, string>,
): string[] {
  if (!Array.isArray(values) || values.length === 0) return [];
  return values.map((value, index) => describeUnknown(value, fallbackPrefix, index, fieldLabelMap));
}

function compareStateFallback(a: PipelineStateNode, b: PipelineStateNode): number {
  return a.order - b.order || a.label.localeCompare(b.label);
}

function computeStateFlowRanks(
  states: PipelineStateNode[],
  transitions: PipelineTransitionEdge[],
  initialStateName: string,
): Map<string, number> {
  const stateById = new Map(states.map((state) => [state.id, state]));
  const adjacency = new Map<string, Set<string>>();

  for (const transition of transitions) {
    if (!stateById.has(transition.sourceId) || !stateById.has(transition.targetId)) continue;
    const nextTargets = adjacency.get(transition.sourceId) ?? new Set<string>();
    nextTargets.add(transition.targetId);
    adjacency.set(transition.sourceId, nextTargets);
  }

  const fallbackStartId = states[0]?.id;
  const startId = initialStateName && stateById.has(initialStateName) ? initialStateName : fallbackStartId;
  if (!startId) return new Map<string, number>();

  const flowRanks = new Map<string, number>([[startId, 0]]);
  const queue: string[] = [startId];

  while (queue.length > 0) {
    const currentId = queue.shift();
    if (!currentId) break;
    const currentRank = flowRanks.get(currentId) ?? 0;
    const sortedTargets = Array.from(adjacency.get(currentId) ?? [])
      .map((targetId) => stateById.get(targetId))
      .filter((state): state is PipelineStateNode => Boolean(state))
      .sort(compareStateFallback);

    for (const target of sortedTargets) {
      if (flowRanks.has(target.id)) continue;
      flowRanks.set(target.id, currentRank + 1);
      queue.push(target.id);
    }
  }

  const maxReachableRank = Math.max(...flowRanks.values());
  const disconnectedBaseRank = maxReachableRank + 1;
  const disconnectedStates = states
    .filter((state) => !flowRanks.has(state.id))
    .sort(compareStateFallback);

  disconnectedStates.forEach((state, index) => {
    flowRanks.set(state.id, disconnectedBaseRank + index);
  });

  return flowRanks;
}

export function deriveViewModel(source: DemoPipelineFile): PipelineViewModel {
  const fieldLabelMap = new Map(
    (source.definition.entity_schema?.fields ?? []).map((field) => [
      field.field,
      field.description || titleCase(field.field),
    ]),
  );

  const initialStateName = source.definition.initial_state;
  const rawTransitions = source.definition.transitions.map((transition) => ({
    id: transition.key,
    sourceId: transition.from,
    targetId: transition.to_state,
    sourceLabel: titleCase(transition.from),
    targetLabel: titleCase(transition.to_state),
    label: transition.label || titleCase(transition.trigger),
    trigger: transition.trigger,
    description: transition.description || transition.label || titleCase(transition.trigger),
    guards: normalizeTextList(transition.guards, 'Guard'),
    requiredFields: normalizeTextList(transition.required_fields, 'Field', fieldLabelMap),
    allowedRoles: normalizeTextList(transition.allowed_roles, 'Role'),
    preTasks: normalizeTextList(transition.pre_transition_tasks, 'Pre-task'),
    postTasks: normalizeTextList(transition.post_transition_tasks, 'Post-task'),
  }));

  const statesByOrder = source.definition.states
    .map<PipelineStateNode>((state) => {
      const tags = state.tags ?? [];
      const isInitial = state.name === initialStateName || tags.includes('initial');
      const isTerminal = tags.includes('terminal');
      const kind: PipelineStateNode['kind'] = isTerminal ? 'terminal' : isInitial ? 'initial' : 'active';
      const incomingTransitionIds = rawTransitions
        .filter((t) => t.targetId === state.name)
        .map((t) => t.id);
      const outgoingTransitionIds = rawTransitions
        .filter((t) => t.sourceId === state.name)
        .map((t) => t.id);

      return {
        id: state.name,
        name: state.name,
        label: titleCase(state.name),
        description: state.description || titleCase(state.name),
        tags,
        order: state.order ?? Number.MAX_SAFE_INTEGER,
        flowRank: Number.MAX_SAFE_INTEGER,
        isInitial,
        isTerminal,
        kind,
        accent: getStateAccent(state.name, kind),
        incomingTransitionIds,
        outgoingTransitionIds,
        incomingCount: incomingTransitionIds.length,
        outgoingCount: outgoingTransitionIds.length,
      };
    })
    .sort(compareStateFallback);

  const flowRanks = computeStateFlowRanks(statesByOrder, rawTransitions, initialStateName);
  const states = statesByOrder.map((state) => ({
    ...state,
    flowRank: flowRanks.get(state.id) ?? Number.MAX_SAFE_INTEGER,
  }));

  const terminalStates = states.filter((s) => s.isTerminal);

  const ENL_PREFIX = '__enl__:';
  const schemaFields = (source.definition.entity_schema?.fields ?? []).map((f) => {
    const desc = f.description ?? '';
    if (desc.startsWith(ENL_PREFIX)) {
      try {
        const meta = JSON.parse(desc.slice(ENL_PREFIX.length)) as { label?: string; enum_labels?: string[] };
        return {
          field: f.field,
          label: meta.label || titleCase(f.field),
          ...(f.enum_values?.length ? { enum_values: f.enum_values } : {}),
          ...(meta.enum_labels?.length ? { enum_labels: meta.enum_labels } : {}),
        };
      } catch {
        // malformed — fall through to default
      }
    }
    return { field: f.field, label: desc || titleCase(f.field) };
  });

  return {
    machineName: source.machine_name || source.definition.name,
    machineVersion: source.base_version,
    entityType: source.definition.entity_type,
    machineDescription: source.definition.description || 'Workflow structure and transition map',
    states,
    terminalStates,
    transitions: rawTransitions,
    schemaFields,
    stateById: new Map(states.map((s) => [s.id, s])),
    transitionById: new Map(rawTransitions.map((t) => [t.id, t])),
  };
}

export function deriveViewModelFromRecord(record: StateMachineRecord): PipelineViewModel {
  const def = record.definition as Record<string, unknown>;
  const rawTransitions = ((def.transitions as unknown[]) ?? []).map((t) => {
    const tr = t as Record<string, unknown>;
    return {
      ...tr,
      from: (tr.from ?? tr.from_state ?? '') as string,
    };
  });

  const pipelineFile: DemoPipelineFile = {
    machine_name: record.machine_name,
    base_version: record.version,
    definition: {
      machine_key: record.machine_key,
      name: record.name,
      description: record.description,
      entity_type: record.entity_type,
      initial_state: (def.initial_state as string) ?? '',
      states: (def.states as DemoPipelineFile['definition']['states']) ?? [],
      transitions: rawTransitions as DemoPipelineFile['definition']['transitions'],
      entity_schema: def.entity_schema as DemoPipelineFile['definition']['entity_schema'],
    },
  };

  return deriveViewModel(pipelineFile);
}
