import { useCallback, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useFeatureFlags } from '@/core/hooks/useFeatureFlags';
import { useSkin } from '@/skins';
import { workflowEntities } from '@/core/services/api';
import { useGlobalEntityFilter } from '@/core/contexts/GlobalEntityFilterContext';
import PipelineKanbanBoard from './components/PipelineKanbanBoard';
import PipelineListView from './components/PipelineListView';
import EntityDetailSlideOver from './components/EntityDetailSlideOver';
import PipelineBoardToolbar from './components/PipelineBoardToolbar';
import { usePipelineBoardData } from './hooks/usePipelineBoardData';
import { usePipelineDragController } from './hooks/usePipelineDragController';
import { moveEntityBetweenColumnCaches, type WorkflowColumnFilters } from './hooks/useWorkflowColumnEntities';
import { usePaginatedPipelineList } from './components/PipelineListView/usePaginatedPipelineList';
import { invalidateWorkflowEntities, patchWorkflowEntityData } from './hooks/workflowEntityCache';
import { useFullWorkflowEntity } from '@/shared/hooks/useFullWorkflowEntity';
import { useHideTerminal } from '@/shared/hooks';
import { usePermissions } from '@/core/hooks/usePermissions';
import { useAuth } from '@/core/auth';
import { useAssigneeFilter } from './hooks/useAssigneeFilter';
import { buildCustomFilterOptions } from './hooks/buildCustomFilterOptions';
import { buildFieldFilters } from './hooks/buildFieldFilters';
import type { FilterBarItem } from '@/skins';

export interface PipelineBoardWidgetProps {
  /** Workflow id — same id as the /pipeline/:id route. */
  workflowId: string;
  view?: 'list' | 'kanban';
  /** Dashboard auto-height mode for the list view; kanban remains fixed-height. */
  autoHeight?: boolean;
  /** List view: per-row transition actions menu. Kanban drag is always transition-enabled. */
  showTransitions?: boolean;
  /**
   * Renders a compact Board/Table + search + "Hide <terminal>" toolbar above
   * the board, and lets the viewer switch views themselves instead of the
   * embedder fixing one via `view`. Used by the agent-mode canvas, which has
   * no page-level chrome of its own.
   */
  showToolbar?: boolean;
  /**
   * When the viewer clicks into an entity's full-page detail, appended as
   * `?returnTo=` so that page's back arrow returns here instead of
   * defaulting to `/pipeline/:id` — e.g. the agent canvas passes `/agent` so
   * clicking back from the detail page lands back in the conversation.
   */
  returnTo?: string;
}

/** One pipeline's board (list or kanban) with full interaction — row/drag
 *  transitions and the entity detail slide-over — for embedding in the
 *  dashboard. Page-level chrome (header, tabs, filters, export, add) stays
 *  on the /pipeline page. */
export default function PipelineBoardWidget({
  workflowId,
  view = 'list',
  autoHeight = false,
  showTransitions = true,
  showToolbar = false,
  returnTo,
}: PipelineBoardWidgetProps) {
  const { skin } = useSkin();
  const queryClient = useQueryClient();
  const { can, canViewField } = usePermissions();
  const { user } = useAuth();
  const { activeAnchorEntityId } = useGlobalEntityFilter();
  const {
    workflow,
    loading,
    error,
    model,
    entitySchemas,
    schemasForState,
    summaryFields,
    canView,
  } = usePipelineBoardData(workflowId);

  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);

  // Only meaningful when `showToolbar` is set — the viewer's own Board/Table
  // choice, seeded from `view` but overriding it from then on (an embedder
  // fixing `view` and also asking for a toolbar makes no sense).
  const [internalView, setInternalView] = useState<'list' | 'kanban'>(view);
  const [search, setSearch] = useState('');
  const { hidden: hideTerminal, setHidden: setHideTerminal } = useHideTerminal();
  const effectiveView = showToolbar ? internalView : view;
  // URL-backed and keyed by machine name (see useAssigneeFilter), same as the
  // main /pipeline page's Board/Table/Calendar — safe to call unconditionally
  // even when `showToolbar` is off, since nothing renders a control for it then.
  const assigneeFilter = useAssigneeFilter(model?.machineName ?? '');

  // Same derivation as the main /pipeline page's "Filters" bubble: any
  // select/boolean schema field the viewer can see becomes an available
  // custom filter; only the ones they've turned on get a control + are
  // actually applied. Local component state rather than URL params — this
  // widget can be embedded more than once at a time (agent canvas), so a
  // shared URL key would make separate boards fight over one filter set.
  const [selectedCustomFilterKeys, setSelectedCustomFilterKeys] = useState<Set<string>>(new Set());
  const [customFilterValues, setCustomFilterValues] = useState<Record<string, string>>({});
  const customFilterOptions = useMemo<FilterBarItem[]>(
    () => (showToolbar && workflow ? buildCustomFilterOptions(entitySchemas, workflow.entity_type, canViewField) : []),
    [showToolbar, workflow, entitySchemas, canViewField],
  );
  const toggleCustomFilter = useCallback((key: string) => {
    setSelectedCustomFilterKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
    setCustomFilterValues((prev) => {
      if (!(key in prev)) return prev;
      const rest = { ...prev };
      delete rest[key];
      return rest;
    });
  }, []);
  const onCustomFilterChange = useCallback((key: string, value: string) => {
    setCustomFilterValues((prev) => ({ ...prev, [key]: value }));
  }, []);
  const fieldFilters = useMemo(() => {
    const optionsByKey = new Map(customFilterOptions.map((option) => [option.key, option]));
    const selectedValues = Object.fromEntries(
      Object.entries(customFilterValues).filter(([key]) => selectedCustomFilterKeys.has(key)),
    );
    return buildFieldFilters(selectedValues, optionsByKey);
  }, [customFilterValues, selectedCustomFilterKeys, customFilterOptions]);

  const navigate = useNavigate();
  const { entityDetailFullPage } = useFeatureFlags();

  const handleEntityClick = (entityId: string, enrollmentWorkflowId?: string) => {
    if (entityDetailFullPage) {
      const query = returnTo ? `?returnTo=${encodeURIComponent(returnTo)}` : '';
      navigate(`/pipeline/${enrollmentWorkflowId ?? workflowId}/entity/${entityId}${query}`);
      return;
    }
    setSelectedEntityId(entityId);
  };

  // Only populated when the workflow has terminal states AND the toolbar's
  // "Hide <terminal>" control is shown — matches the main /pipeline page's
  // exclude_states behaviour.
  const terminalStateNames = useMemo(
    () => (model?.terminalStates ?? []).map((s) => s.name),
    [model],
  );
  const excludeStates = showToolbar && hideTerminal ? terminalStateNames : undefined;

  const columnFilters: WorkflowColumnFilters = useMemo(
    // `anchorEntityId` carries the app-shell global entity filter — the
    // paginated hooks take it as a param rather than reading the context
    // themselves, so omitting it here would make this widget ignore an
    // active org-wide scope.
    () => ({
      thumbnailField: skin.board.thumbnailDataField,
      summaryFields,
      anchorEntityId: activeAnchorEntityId,
      search: showToolbar ? search : undefined,
      fieldFilters: showToolbar && Object.keys(fieldFilters).length ? fieldFilters : undefined,
      assigneeIds: showToolbar && assigneeFilter.selectedIds.length ? assigneeFilter.selectedIds : undefined,
      excludeStates,
    }),
    [
      skin.board.thumbnailDataField,
      summaryFields,
      activeAnchorEntityId,
      showToolbar,
      search,
      fieldFilters,
      assigneeFilter.selectedIds,
      excludeStates,
    ],
  );

  const refetchEntities = useCallback(async () => {
    invalidateWorkflowEntities(queryClient);
  }, [queryClient]);

  const drag = usePipelineDragController({
    model,
    patchEntityState: (entityId, fromStateId, toStateId) => {
      if (!model) return;
      moveEntityBetweenColumnCaches(queryClient, model.machineName, columnFilters, entityId, fromStateId, toStateId);
    },
    onTransitionCommitted: () => void refetchEntities(),
  });

  const tableController = usePaginatedPipelineList(
    model ?? { machineName: '', machineVersion: 0, entityType: '', machineDescription: '', states: [], terminalStates: [], transitions: [], schemaFields: [], stateById: new Map(), transitionById: new Map() },
    model?.machineName ?? '',
    {
      entitySchemas,
      thumbnailField: skin.board.thumbnailDataField,
      summaryFields,
      search: showToolbar ? search : undefined,
      onSearchChange: showToolbar ? setSearch : undefined,
      anchorEntityId: activeAnchorEntityId,
      // No `assigneeIds` option here — `usePaginatedPipelineList` already
      // reads the same URL-backed `useAssigneeFilter(machineName)` selection
      // internally, so the Table view applies it without being told.
      fieldFilters: showToolbar && Object.keys(fieldFilters).length ? fieldFilters : undefined,
      excludeStates,
      enabled: effectiveView === 'list',
    },
  );

  const patchEntityData = useCallback(
    (entityId: string, data: Record<string, unknown>) => patchWorkflowEntityData(queryClient, entityId, data),
    [queryClient],
  );
  const updateEntity = useCallback(
    async (entityId: string, payload: Parameters<typeof workflowEntities.update>[1]) => {
      await workflowEntities.update(entityId, payload);
    },
    [],
  );

  const { data: detailSummary } = useQuery({
    queryKey: ['workflowEntitySummary', selectedEntityId],
    queryFn: () => workflowEntities.get(selectedEntityId ?? ''),
    enabled: Boolean(selectedEntityId),
  });
  const { entity: detailEntity } = useFullWorkflowEntity(detailSummary ?? null);

  if (loading) {
    return <div className="text-sm text-muted-foreground">Loading pipeline…</div>;
  }
  if (error || !workflow || !model) {
    return (
      <div className="text-sm text-destructive">
        {error ?? 'Pipeline not found. Edit the widget and pick another pipeline.'}
      </div>
    );
  }
  if (!canView) {
    return (
      <div className="text-sm text-muted-foreground">
        You don't have permission to view this pipeline.
      </div>
    );
  }

  return (
    <div className={autoHeight && effectiveView === 'list' ? 'flex flex-col' : 'flex h-full min-h-0 flex-col'}>
      {showToolbar && (
        <PipelineBoardToolbar
          view={internalView}
          onViewChange={setInternalView}
          search={search}
          onSearchChange={setSearch}
          terminalToggle={
            terminalStateNames.length > 0
              ? {
                  hidden: hideTerminal,
                  label: model.terminalStates.length === 1 ? model.terminalStates[0].label : 'Terminal',
                  onToggle: setHideTerminal,
                }
              : undefined
          }
          customFilters={
            customFilterOptions.length > 0
              ? {
                  available: customFilterOptions,
                  selectedKeys: selectedCustomFilterKeys,
                  onToggleAvailable: toggleCustomFilter,
                  values: customFilterValues,
                  onChange: onCustomFilterChange,
                }
              : undefined
          }
          assigneeFilter={
            assigneeFilter.options.length > 0
              ? {
                  options: assigneeFilter.options,
                  hasUnassigned: assigneeFilter.hasUnassigned,
                  selectedIds: assigneeFilter.selectedIds,
                  onToggle: assigneeFilter.toggle,
                  onClear: assigneeFilter.clear,
                  currentUserId: user?.id,
                }
              : undefined
          }
        />
      )}
      {effectiveView === 'kanban' ? (
        <div className="flex min-h-0 flex-1 overflow-hidden">
          <PipelineKanbanBoard
            machineName={model.machineName}
            filters={columnFilters}
            model={model}
            activeEntityId={drag.activeEntityId}
            activeStateId={drag.activeStateId}
            hoveredStateId={drag.hoveredStateId}
            invalidStateId={drag.invalidStateId}
            allowedTargetIds={drag.allowedTargetIds}
            onDragStart={drag.onDragStart}
            onDragOver={drag.onDragOver}
            onDragEnd={drag.onDragEnd}
            onEntityClick={handleEntityClick}
            canDelete={can('delete', workflow.entity_type)}
            onBulkMutationCommitted={() => void refetchEntities()}
            entityLabel={workflow.entity_type.replace(/^[^.]+\./i, '').toLowerCase()}
          />
        </div>
      ) : (
        <div className={autoHeight ? 'overflow-auto' : 'min-h-0 flex-1 overflow-auto'}>
          <PipelineListView
            key={model.machineName}
            model={model}
            controller={tableController}
            onEntityClick={handleEntityClick}
            showAssignee
            showSearch={!showToolbar}
            enableRowTransitions={showTransitions}
            enableBulkActions
            canDelete={can('delete', workflow.entity_type)}
            onTransitionExecuted={() => void refetchEntities()}
            onBulkMutationCommitted={() => void refetchEntities()}
          />
        </div>
      )}

      <EntityDetailSlideOver
        entity={detailEntity}
        open={detailEntity !== null}
        onClose={() => {
          setSelectedEntityId(null);
        }}
        // Same strict rule as the other detail surfaces: only the fields the
        // record's current state collects.
        schemas={schemasForState(detailEntity?.current_state)}
        schemasAuthoritative
        onSaveEntity={updateEntity}
        onFileUploaded={() => void refetchEntities()}
        workflowId={workflowId}
        onTransitionExecuted={() => {
          void refetchEntities();
          setSelectedEntityId(null);
        }}
        onEntityDataSaved={(newData) => {
          if (!selectedEntityId) return;
          patchEntityData(selectedEntityId, newData);
          void refetchEntities();
        }}
        onDeleted={() => {
          void refetchEntities();
          setSelectedEntityId(null);
        }}
      />
    </div>
  );
}
