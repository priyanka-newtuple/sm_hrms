import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ListChecks } from 'lucide-react';
import { useAuth } from '@/core/auth';
import { useFormSchemas } from '@/core/hooks';
import { isAdminRole } from '@/core/utils';
import { useFeatureFlags } from '@/core/hooks/useFeatureFlags';
import { useStateMachinesList } from '@/core/hooks/useStateMachinesList';
import { deriveViewModelFromRecord } from '@/shared/utils/pipelineViewModel';
import {
  useAllWorkflowEntities,
  useAppLabels,
  useColumnLabels,
  useEntitySchemasFor,
  useHideTerminal,
  useWorkflow,
  useWorkflows,
} from '@/shared/hooks';
import { useFullWorkflowEntity } from '@/shared/hooks/useFullWorkflowEntity';
import { buildFallbackFormSchemaFromEntitySchema } from '@/lib/state-machine/entitySchema';
import type { StateMachineDefinition } from '@/lib/state-machine/types';
import { resolveFullWorkflowEntityDisplay } from '@/shared/hooks/fullWorkflowEntityIdentity';
import type { PipelineListEntity, PipelineViewModel } from '@/shared/types/pipeline';
import type { WorkflowEntityState } from '@/core/services/api';
import { workflowEntities } from '@/core/services/api';
import { getFormFields } from '@/shared/utils/entityForm';
import PipelineListView from '../Pipeline/components/PipelineListView';
import EntityDetailSlideOver from '../Pipeline/components/EntityDetailSlideOver';
import PipelineTerminalToggle from '../Pipeline/components/PipelineTerminalToggle';
import type { ColumnField } from '../Pipeline/components/PipelineListView/types';

/** Synthetic model: the aggregated view has no single workflow definition.
 *  States are heterogeneous across workflows, so the colored state map is
 *  empty and rows fall back to a neutral badge showing the raw state name. */
const AGGREGATE_MODEL: PipelineViewModel = {
  machineName: 'all-workflows',
  machineVersion: 0,
  entityType: 'workflow',
  machineDescription: '',
  states: [],
  terminalStates: [],
  transitions: [],
  schemaFields: [],
  stateById: new Map(),
  transitionById: new Map(),
};

const DEFAULT_VISIBLE_FIELDS = ['workflow', 'owner'];

function normalizeEntityTypeKey(entityType: string | undefined): string {
  return (entityType ?? '').replace(/^ATS\./i, '').trim().toLowerCase();
}

function toListEntity(entity: WorkflowEntityState): PipelineListEntity {
  const createdAt =
    entity.created_at ??
    entity.state_entered_at ??
    entity.last_transition_at ??
    entity.updated_at ??
    new Date().toISOString();
  const updatedAt =
    entity.updated_at ?? entity.last_transition_at ?? entity.state_entered_at ?? createdAt;

  return {
    entity_id: entity.entity_id,
    state_id: entity.state_id,
    workflow_id: entity.workflow_id,
    current_state: entity.current_state,
    current_state_description: entity.current_state_description,
    created_at: createdAt,
    updated_at: updatedAt,
    due_date: entity.due_date,
    data: entity.data,
    machine_name: entity.machine_name || undefined,
    owner_name: entity.owner_name,
    entity_type: entity.entity_type,
    transition_options: entity.transition_options,
  };
}

export interface WorkflowsListWidgetProps {
  /** Render the "Workflows" heading block. The page shows it; the dashboard hides it by default. */
  showHeader?: boolean;
  /** Dashboard mode: fill the parent container instead of page-scale spacing. */
  compact?: boolean;
  /** Dashboard auto-height mode: size to list content when it fits below the user's max. */
  autoHeight?: boolean;
  /** Initial entity-type filter; the toolbar dropdown can still change it. */
  entityTypeFilter?: string;
  /** Field ids visible by default (falls back to workflow + owner). */
  defaultVisibleFields?: string[];
  /** Per-row transition actions menu. */
  showTransitions?: boolean;
}

/** The full interactive workflows list + entity detail slide-over, reusable by
 *  the /workflows page and the dashboard's embedded widget. */
export default function WorkflowsListWidget({
  showHeader = true,
  compact = false,
  autoHeight = false,
  entityTypeFilter: initialEntityTypeFilter,
  defaultVisibleFields,
  showTransitions = true,
}: WorkflowsListWidgetProps) {
  const { entities, refetch } = useAllWorkflowEntities();
  const { workflows } = useWorkflows();
  const { schemas: allSchemas } = useFormSchemas();
  const labels = useColumnLabels();
  const appLabels = useAppLabels();

  const [entityTypeFilter, setEntityTypeFilter] = useState(initialEntityTypeFilter ?? '');
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string | null>(null);

  const navigate = useNavigate();
  const { entityDetailFullPage } = useFeatureFlags();
  const { user } = useAuth();

  // Org-wide, same value as the Pipeline board toolbar and Settings → Display
  // (organization.settings.featureFlags.hideTerminalByDefault).
  const { hidden: hideTerminal, setHidden: setHideTerminal } = useHideTerminal();
  const canManageTerminalVisibility = isAdminRole(user?.role);

  // Each workflow VERSION can define its own terminal states, and entities stay
  // enrolled against the version they started on — so this must key by
  // machine_name + machine_version, not collapse to each machine's latest version.
  const { data: machineRecords } = useStateMachinesList();
  const terminalStateNamesByMachineVersion = useMemo(() => {
    const map = new Map<string, Set<string>>();
    for (const rec of machineRecords ?? []) {
      const vm = deriveViewModelFromRecord(rec);
      map.set(`${rec.machine_name}::${rec.version}`, new Set(vm.terminalStates.map((s) => s.name)));
    }
    return map;
  }, [machineRecords]);
  const hasTerminalStates = useMemo(
    () => Array.from(terminalStateNamesByMachineVersion.values()).some((s) => s.size > 0),
    [terminalStateNamesByMachineVersion],
  );

  // Cross-workflow list: the full-page route needs the row's own workflow id.
  // Rows without one (orphaned entities) fall back to the sheet.
  const handleEntityClick = (entityId: string, workflowId?: string) => {
    if (entityDetailFullPage && workflowId) {
      navigate(`/pipeline/${workflowId}/entity/${entityId}`);
      return;
    }
    setSelectedEntityId(entityId);
    setSelectedWorkflowId(workflowId ?? null);
  };

  // Friendly workflow display name (def.name) keyed by machine_name (slug).
  const labelBySlug = useMemo(() => {
    const map = new Map<string, string>();
    for (const wf of workflows) map.set(wf.slug, wf.label);
    return map;
  }, [workflows]);

  const extraColumns = useMemo<ColumnField[]>(
    () => [
      {
        field: 'workflow',
        label: labels.workflow,
        accessor: (e) => (e.machine_name ? labelBySlug.get(e.machine_name) ?? e.machine_name : ''),
      },
      { field: 'owner', label: labels.owner, accessor: (e) => e.owner_name },
    ],
    [labelBySlug, labels.workflow, labels.owner],
  );

  // Distinct entity types across all results power the type dropdown.
  const entityTypes = useMemo(
    () =>
      Array.from(
        new Set(entities.map((e) => e.entity_type).filter((t): t is string => Boolean(t))),
      ).sort(),
    [entities],
  );

  // Distinct current states (heterogeneous across workflows) power the state filter.
  const stateOptions = useMemo(
    () =>
      Array.from(new Set(entities.map((e) => e.current_state).filter(Boolean)))
        .sort()
        .map((s) => ({ id: s, label: s })),
    [entities],
  );

  const listEntities = useMemo(() => {
    let filtered = entityTypeFilter
      ? entities.filter((e) => e.entity_type === entityTypeFilter)
      : entities;
    if (hideTerminal) {
      filtered = filtered.filter((e) => {
        const terminalNames = e.machine_name
          ? terminalStateNamesByMachineVersion.get(`${e.machine_name}::${e.machine_version}`)
          : undefined;
        return !terminalNames?.has(e.current_state);
      });
    }
    return filtered.map(toListEntity);
  }, [entities, entityTypeFilter, hideTerminal, terminalStateNamesByMachineVersion]);
  const [visibleEntities, setVisibleEntities] = useState(listEntities);
  const [visibleBaseline, setVisibleBaseline] = useState(listEntities);
  if (visibleBaseline !== listEntities) {
    setVisibleBaseline(listEntities);
    setVisibleEntities(listEntities);
  }
  const listFieldMetaByEntityType = useMemo(() => {
    const byType = new Map<
      string,
      Map<string, { type?: string; enum_values?: string[]; enum_labels?: string[] }>
    >();
    for (const schema of allSchemas) {
      if (!schema.is_active) continue;
      const typeKey = normalizeEntityTypeKey(schema.entity_type);
      if (!typeKey) continue;
      const fields = byType.get(typeKey) ?? new Map<string, { type?: string; enum_values?: string[]; enum_labels?: string[] }>();
      for (const field of getFormFields(schema)) {
        if (!field.enum_values?.length || fields.has(field.id)) continue;
        fields.set(field.id, {
          type: field.type,
          enum_values: field.enum_values,
          enum_labels: field.enum_labels,
        });
      }
      byType.set(typeKey, fields);
    }
    return byType;
  }, [allSchemas]);
  const resolveListFieldMeta = useMemo(
    () =>
      (entity: PipelineListEntity, fieldId: string) =>
        listFieldMetaByEntityType.get(normalizeEntityTypeKey(entity.entity_type))?.get(fieldId),
    [listFieldMetaByEntityType],
  );

  const selectedSummary = useMemo(
    () => entities.find(
      (e) => e.entity_id === selectedEntityId
        && (!selectedWorkflowId || e.workflow_id === selectedWorkflowId),
    ) ?? null,
    [entities, selectedEntityId, selectedWorkflowId],
  );
  const {
    entity: selectedEntity,
    loading: selectedEntityLoading,
    error: selectedEntityError,
  } = useFullWorkflowEntity(selectedSummary);
  const {
    displayedEntity,
    displayLoading: detailLoading,
  } = resolveFullWorkflowEntityDisplay(
    selectedSummary,
    selectedEntity,
    selectedEntityLoading,
    selectedEntityError,
  );
  const selectedEntityIndex = visibleEntities.findIndex(
    (entity) =>
      entity.entity_id === selectedEntityId
      && (!selectedWorkflowId || entity.workflow_id === selectedWorkflowId),
  );
  const navigateSelectedEntity = (offset: -1 | 1) => {
    const target = visibleEntities[selectedEntityIndex + offset];
    if (!target) return;
    setSelectedEntityId(target.entity_id);
    setSelectedWorkflowId(target.workflow_id ?? null);
  };

  // Schemas for the selected entity's type drive the detail form tabs.
  const formSchemas = useEntitySchemasFor(selectedSummary?.entity_type);
  // An entity type whose fields come from Method Blocks has no Forms config, so
  // fall back to the workflow's own resolved entity_schema — scoped to the
  // record's current state, matching every other detail surface. A real form
  // always wins; this only fills a genuine absence.
  const { workflow: selectedWorkflow } = useWorkflow(selectedSummary?.workflow_id ?? undefined);
  const schemas = useMemo(() => {
    if (formSchemas.length > 0) return formSchemas;
    const definition = selectedWorkflow?.definition as StateMachineDefinition | undefined;
    const fields = definition?.entity_schema?.fields;
    const entityType = selectedSummary?.entity_type;
    if (!entityType || !fields?.length) return formSchemas;
    const fallback = buildFallbackFormSchemaFromEntitySchema(entityType, fields, {
      stateName: displayedEntity?.current_state,
      requireState: true,
    });
    return fallback ? [fallback] : formSchemas;
  }, [formSchemas, selectedWorkflow, selectedSummary?.entity_type, displayedEntity?.current_state]);

  return (
    <div
      className={
        compact && autoHeight
          ? 'flex flex-col gap-3'
          : compact
            ? 'flex h-full min-h-0 flex-col gap-3'
            : 'flex h-full min-h-0 flex-col gap-6'
      }
    >
      {showHeader && (
        <div className="flex shrink-0 items-start justify-between gap-4">
          <div>
            <h1 className="flex items-center gap-2 text-xl font-semibold text-foreground">
              <ListChecks className="h-5 w-5 text-cobalt" />
              {appLabels.workflows}
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Every entity across all workflows in your organization.
            </p>
          </div>
          {hasTerminalStates && canManageTerminalVisibility && (
            <PipelineTerminalToggle hidden={hideTerminal} label="Terminal Entities" onToggle={setHideTerminal} />
          )}
        </div>
      )}

      <div className={autoHeight ? 'overflow-auto' : 'min-h-0 flex-1 overflow-auto'}>
        <PipelineListView
          model={AGGREGATE_MODEL}
          entities={listEntities}
          extraColumns={extraColumns}
          defaultVisibleFields={
            defaultVisibleFields?.length ? defaultVisibleFields : DEFAULT_VISIBLE_FIELDS
          }
          entityTypes={entityTypes}
          entityTypeFilter={entityTypeFilter}
          onEntityTypeFilterChange={setEntityTypeFilter}
          stateOptions={stateOptions}
          showCreated={false}
          enableRowTransitions={showTransitions}
          resolveFieldMeta={resolveListFieldMeta}
          onTransitionExecuted={() => void refetch()}
          onEntityClick={handleEntityClick}
          onFilteredEntitiesChange={setVisibleEntities}
        />
      </div>

      <EntityDetailSlideOver
        entity={displayedEntity}
        open={selectedSummary !== null}
        loading={detailLoading}
        onClose={() => {
          setSelectedEntityId(null);
          setSelectedWorkflowId(null);
        }}
        schemas={schemas}
        schemasAuthoritative
        workflowId={selectedSummary?.workflow_id}
        onSaveEntity={async (entityId, payload) => {
          await workflowEntities.update(entityId, payload);
        }}
        onEntityDataSaved={() => void refetch()}
        onTransitionExecuted={() => {
          void refetch();
          setSelectedEntityId(null);
          setSelectedWorkflowId(null);
        }}
        iterator={
          selectedEntityIndex >= 0
            ? {
                current: selectedEntityIndex + 1,
                total: visibleEntities.length,
                onPrevious: () => navigateSelectedEntity(-1),
                onNext: () => navigateSelectedEntity(1),
              }
            : undefined
        }
      />
    </div>
  );
}
