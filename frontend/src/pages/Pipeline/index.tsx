import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { CalendarDays, LayoutGrid, ListChecks, UploadCloud } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import AccessDenied from '@/core/components/AccessDenied';
import type { PipelineListEntity } from '@/shared/types/pipeline';
import { resolveEntityTypeLabel } from '@/shared/utils/labels';
import { workflowEntities } from '@/core/services/api';
import type { WorkflowEntityState } from '@/core/services/api';
import { useAuth } from '@/core/auth';
import { useGlobalEntityFilter } from '@/core/contexts/GlobalEntityFilterContext';
import { isAdminRole } from '@/core/utils';
import { useSkin } from '@/skins';
import { ComponentSlot } from '@/core/componentRegistry';
import PipelineKanbanBoard from './components/PipelineKanbanBoard';
import PipelineListView from './components/PipelineListView';
import PipelineCalendarView from './components/PipelineCalendarView';
import EntityDetailSlideOver from './components/EntityDetailSlideOver';
import AddEntityDialog from './components/AddEntityDialog';
import PipelinePageHeader from './components/PipelinePageHeader';
import BoardFilterBar from './components/BoardFilterBar';
import BoardCustomFilters from './components/BoardCustomFilters';
import PipelineTerminalToggle from './components/PipelineTerminalToggle';
import ExportDropdown from './components/ExportDropdown';
import ExportCsvButton from './components/ExportCsvButton';
import { usePipelineBoardData, toListEntity } from './hooks/usePipelineBoardData';
import { useKanbanCardFieldsToolbar } from './hooks/useKanbanCardFieldsToolbar';
import { buildCustomFilterOptions } from './hooks/buildCustomFilterOptions';
import { buildFieldFilters } from './hooks/buildFieldFilters';
import { usePipelineDragController } from './hooks/usePipelineDragController';
import { moveEntityBetweenColumnCaches, type WorkflowColumnFilters } from './hooks/useWorkflowColumnEntities';
import { usePaginatedPipelineList } from './components/PipelineListView/usePaginatedPipelineList';
import { invalidateWorkflowEntities, patchWorkflowEntityData } from './hooks/workflowEntityCache';
import { useBoardFilters } from './hooks/useBoardFilters';
import { useAssigneeFilter } from './hooks/useAssigneeFilter';
import AssigneeAvatarFilter from './components/PipelineListView/AssigneeAvatarFilter';
import { FIELD_GROUP, type ColumnField } from './components/PipelineListView/types';
import { useFeatureFlags } from '@/core/hooks/useFeatureFlags';
import { useColumnLabels, useHideTerminal, useNavLayout, useWorkflowEntities as useWorkflowEntitiesFullDrain } from '@/shared/hooks';
import { getIdentifierLabel, getFormFields } from '@/shared/utils/entityForm';
import { cn } from '@/lib/utils';
import { useFullWorkflowEntity } from '@/shared/hooks/useFullWorkflowEntity';
import { resolveFullWorkflowEntityDisplay } from '@/shared/hooks/fullWorkflowEntityIdentity';
import { usePermissions } from '@/core/hooks/usePermissions';
import type { FilterBarItem } from '@/skins';

const EMPTY_FILTER_CONFIG: NonNullable<ReturnType<typeof useSkin>['skin']['board']['filterBar']> = [];
const DEFAULT_SEARCH_FILTER: FilterBarItem = {
  key: 'search',
  label: 'Search',
  type: 'search',
  placeholder: 'Search this workflow…',
};
const CUSTOM_FILTERS_PARAM = 'board_filter_fields';

// Placeholder passed to the detail slot before a real entity is selected.
// Typed as WorkflowEntityState so a newly-required field fails to compile here
// rather than silently producing an invalid entity at runtime.
const EMPTY_ENTITY: WorkflowEntityState = {
  entity_id: '',
  entity_type: '',
  organization_id: '',
  machine_name: '',
  machine_version: 1,
  current_state: '',
  state_version: 0,
  data: {},
};

export default function PipelinePage() {
  const { id } = useParams<{ id: string }>();
  const { skin } = useSkin();
  const { user } = useAuth();
  const navigate = useNavigate();
  const navLayout = useNavLayout();
  const queryClient = useQueryClient();
  const { can, canViewField, hasPermission } = usePermissions();
  const labels = useColumnLabels();
  const { activeAnchorEntityId } = useGlobalEntityFilter();
  const { hideKanban, hideCalendar, hideDueDate, hideExport, entityDetailFullPage, bulkImportEnabled, cardFieldsEnabled } = useFeatureFlags();
  const showCalendar = !hideCalendar && !hideDueDate;
  // Skins can replace the detail view via the `entity-detail-view` slot; the
  // full-page route bypasses that slot, so the flag is ignored when a custom
  // detail component is registered — those orgs keep their skinned sheet.
  const fullPageEnabled = entityDetailFullPage && !skin.components?.['entity-detail-view'];
  const {
    workflow,
    loading,
    error: fetchError,
    model,
    entitySchemas,
    creationSchemas,
    schemasForState,
    entitySchemasLoading,
    entitySchemasError,
    summaryFields,
    builtInCardFields,
    canView,
    canCreate,
  } = usePipelineBoardData(id);

  const [searchParams, setSearchParams] = useSearchParams();
  const entityParam = searchParams.get('entity');
  const enrollmentWorkflowParam = searchParams.get('workflow');
  const tabParam = searchParams.get('tab');
  const commentParam = searchParams.get('comment');
  const replyParam = searchParams.get('reply');

  // Keep the no-filter fallback referentially stable. A fresh array on every
  // render changes useBoardFilters' callback, which can cascade into the
  // list/export render-time synchronization and cause an infinite render loop.
  const skinFilterConfig = skin.board.filterBar ?? EMPTY_FILTER_CONFIG;
  const customFilterOptions = useMemo<FilterBarItem[]>(
    () => (workflow ? buildCustomFilterOptions(entitySchemas, workflow.entity_type, canViewField) : []),
    [canViewField, entitySchemas, workflow],
  );
  // Intersected against customFilterOptions, not the raw URL param — a key
  // enabled for a field that was since removed/renamed in the entity schema
  // (or just isn't a filterable field type) would otherwise inflate the
  // "Filters (N)" badge with a key that renders no checkbox in the
  // customize-filters popover, and can then never be unchecked from the UI.
  const selectedCustomFilterKeys = useMemo(() => {
    const raw = new Set((searchParams.get(CUSTOM_FILTERS_PARAM) ?? '').split(',').filter(Boolean));
    const availableKeys = new Set(customFilterOptions.map((filter) => filter.key));
    return new Set([...raw].filter((key) => availableKeys.has(key)));
  }, [searchParams, customFilterOptions]);
  const filterConfig = useMemo(() => {
    const configured = skinFilterConfig.some((filter) => filter.type === 'search')
      ? skinFilterConfig
      : [DEFAULT_SEARCH_FILTER, ...skinFilterConfig];
    const keys = new Set(configured.map((filter) => filter.key));
    return [
      ...configured,
      ...customFilterOptions.filter((filter) => selectedCustomFilterKeys.has(filter.key) && !keys.has(filter.key)),
    ];
  }, [customFilterOptions, selectedCustomFilterKeys, skinFilterConfig]);
  const { values: filterValues, onChange: onFilterChange } = useBoardFilters(filterConfig);
  const toggleCustomFilter = useCallback((key: string) => {
    setSearchParams((previous) => {
      const next = new URLSearchParams(previous);
      const selected = new Set((next.get(CUSTOM_FILTERS_PARAM) ?? '').split(',').filter(Boolean));
      if (selected.has(key)) {
        selected.delete(key);
        next.delete(`filter_${key}`);
      } else {
        selected.add(key);
      }
      if (selected.size) next.set(CUSTOM_FILTERS_PARAM, Array.from(selected).sort().join(','));
      else next.delete(CUSTOM_FILTERS_PARAM);
      return next;
    }, { replace: true });
  }, [setSearchParams]);
  const searchValue = useMemo(() => {
    const activeSearch = filterConfig.find(
      (filter) => filter.type === 'search' && filterValues[filter.key],
    );
    return activeSearch ? filterValues[activeSearch.key] : undefined;
  }, [filterConfig, filterValues]);
  const searchFilterKey = useMemo(
    () => filterConfig.find((filter) => filter.type === 'search')?.key,
    [filterConfig],
  );
  const onSharedSearchChange = useCallback((value: string) => {
    if (searchFilterKey) onFilterChange(searchFilterKey, value);
  }, [onFilterChange, searchFilterKey]);
  const fieldFilters = useMemo(() => {
    const optionsByKey = new Map(filterConfig.map((filter) => [filter.key, filter]));
    return buildFieldFilters(filterValues, optionsByKey);
  }, [filterConfig, filterValues]);
  // Shared across Board/Table/Calendar — one URL-backed selection per workflow.
  const assigneeFilter = useAssigneeFilter(model?.machineName ?? '');

  // Which top-level view (Board/List/Calendar) is active — kept in the URL,
  // like every other piece of view state on this page (`entity`, `workflow`,
  // `comment`), so refreshing or sharing a link doesn't silently drop back to
  // the default view. `view` is distinct from `tab`, which scopes the entity
  // detail panel's own sub-tabs. Resolved up here, ahead of every data hook,
  // because each view's fetch is gated on being the active one — a view that
  // isn't on screen must not spend requests.
  const validViews = useMemo(() => {
    const views = ['list'];
    if (!hideKanban) views.push('kanban');
    if (showCalendar) views.push('calendar');
    return views;
  }, [hideKanban, showCalendar]);
  const defaultView = hideKanban ? 'list' : 'kanban';
  const viewParam = searchParams.get('view');
  const activeView = viewParam && validViews.includes(viewParam) ? viewParam : defaultView;
  const setActiveView = useCallback(
    (view: string) => {
      setSearchParams((p) => {
        p.set('view', view);
        return p;
      });
    },
    [setSearchParams],
  );

  // Names of this workflow's terminal states (from the definition's `terminal`
  // tag) — sent to the backend as `exclude_states` when hidden, instead of a
  // client-side filter over an in-memory array.
  const terminalStateNames = useMemo(
    () => (model?.terminalStates ?? []).map((s) => s.name),
    [model],
  );
  // Org-wide, same value on every board — persisted server-side
  // (organization.settings.featureFlags.hideTerminalByDefault).
  const { hidden: hideTerminal, setHidden: setHideTerminal } = useHideTerminal();

  // Up to 3 extra entity fields an admin configured to show on this
  // workflow's Kanban cards — backend-persisted per-workflow (unlike the
  // Table view's Columns picker), so it's shared by everyone viewing this
  // board. Card rendering needs the actual field values, so they're unioned
  // into the Kanban-only fields request below; Table/Calendar keep using
  // `summaryFields` untouched.
  const { toggle: cardFieldsToggle, kanbanSummaryFields, selectedCardFieldMeta } = useKanbanCardFieldsToolbar(
    model?.machineName ?? '',
    entitySchemas,
    summaryFields,
    {
      enabled: cardFieldsEnabled,
      isKanbanView: activeView === 'kanban',
      builtInCardFields,
      canViewField: workflow ? (fieldId) => canViewField(workflow.entity_type, fieldId) : undefined,
      canConfigure: hasPermission('workflow:write'),
    },
  );

  const columnFilters: WorkflowColumnFilters = useMemo(
    () => ({
      thumbnailField: skin.board.thumbnailDataField,
      summaryFields: kanbanSummaryFields,
      search: searchValue,
      fieldFilters: Object.keys(fieldFilters).length ? fieldFilters : undefined,
      // The app-shell global entity filter. `useWorkflowEntities` (Calendar)
      // reads it from the context itself; the Kanban/Table hooks take it as a
      // param, so this page has to pass it or those two tabs silently ignore
      // an active org-wide scope that Calendar still honours.
      anchorEntityId: activeAnchorEntityId,
      assigneeIds: assigneeFilter.selectedIds.length ? assigneeFilter.selectedIds : undefined,
      excludeStates: hideTerminal ? terminalStateNames : undefined,
    }),
    [skin.board.thumbnailDataField, kanbanSummaryFields, searchValue, fieldFilters, activeAnchorEntityId, assigneeFilter.selectedIds, hideTerminal, terminalStateNames],
  );

  const drag = usePipelineDragController({
    model,
    patchEntityState: (entityId, fromStateId, toStateId) => {
      if (!model) return;
      moveEntityBetweenColumnCaches(queryClient, model.machineName, columnFilters, entityId, fromStateId, toStateId);
    },
    onTransitionCommitted: () => invalidateWorkflowEntities(queryClient),
  });

  // The Table tab's own fixed/structural columns — mirrors what
  // PipelineListView computes internally for its uncontrolled (entities-prop)
  // path, needed here too since usePaginatedPipelineList is now built by this
  // page rather than by PipelineListView itself.
  const tableFixedColumns = useMemo<ColumnField[]>(() => {
    const cols: ColumnField[] = [
      { field: 'entity', label: labels.entity, group: FIELD_GROUP.STANDARD },
      { field: 'identifier', label: getIdentifierLabel(model?.entityType ?? ''), group: FIELD_GROUP.STANDARD },
    ];
    if (!hideDueDate) cols.push({ field: 'due_date', label: 'Due date', group: FIELD_GROUP.STANDARD });
    cols.push({ field: 'state', label: labels.state, group: FIELD_GROUP.STANDARD });
    cols.push({ field: 'assignee', label: 'Owner', group: FIELD_GROUP.STANDARD });
    cols.push({ field: 'created', label: labels.created, group: FIELD_GROUP.STANDARD });
    return cols;
  }, [model?.entityType, hideDueDate, labels.entity, labels.state, labels.created]);

  const tableController = usePaginatedPipelineList(
    model ?? { machineName: '', machineVersion: 0, entityType: '', machineDescription: '', states: [], terminalStates: [], transitions: [], schemaFields: [], stateById: new Map(), transitionById: new Map() },
    model?.machineName ?? '',
    {
      fixedColumns: tableFixedColumns,
      entitySchemas,
      thumbnailField: skin.board.thumbnailDataField,
      summaryFields,
      search: searchValue ?? '',
      onSearchChange: onSharedSearchChange,
      fieldFilters: Object.keys(fieldFilters).length ? fieldFilters : undefined,
      anchorEntityId: activeAnchorEntityId,
      // Same hide-terminal exclusion the Kanban columns get — all three views
      // have to agree on which records exist.
      excludeStates: hideTerminal ? terminalStateNames : undefined,
      enabled: activeView === 'list',
    },
  );

  // Calendar is out of scope for pagination this pass — still a full
  // client-side drain (one request per state, each draining every page), so
  // it must stay gated on the Calendar tab being the ACTIVE one, not merely
  // available: gating on `showCalendar` fires N-states requests on the
  // Kanban/Table tabs too, which is exactly the cost this refactor removes.
  // Hide-terminal is applied by simply not asking for those states — this hook
  // fetches per state, so dropping them from the list is the exclusion.
  const calendarStateNames = useMemo(() => {
    const names = model?.states.map((state) => state.name) ?? [];
    if (!hideTerminal) return names;
    const terminal = new Set(terminalStateNames);
    return names.filter((name) => !terminal.has(name));
  }, [model?.states, hideTerminal, terminalStateNames]);
  const { entities: calendarEntities } = useWorkflowEntitiesFullDrain(
    model?.machineName,
    skin.board.thumbnailDataField,
    {
      stateNames: calendarStateNames,
      summaryFields,
      // An empty `stateNames` means "no state filter" to this hook, i.e. fetch
      // everything — so if hide-terminal excluded every state, asking at all
      // would invert into showing all of them. Don't ask.
      enabled: activeView === 'calendar' && calendarStateNames.length > 0,
    },
  );
  const calendarListEntities = useMemo(() => calendarEntities.map(toListEntity), [calendarEntities]);

  const listFieldMetaById = useMemo(() => {
    const map = new Map<string, { type?: string; enum_values?: string[]; enum_labels?: string[] }>();
    for (const schema of entitySchemas) {
      for (const field of getFormFields(schema)) {
        if (!field.enum_values?.length || map.has(field.id)) continue;
        map.set(field.id, {
          type: field.type,
          enum_values: field.enum_values,
          enum_labels: field.enum_labels,
        });
      }
    }
    return map;
  }, [entitySchemas]);
  const resolveListFieldMeta = useCallback(
    (_entity: PipelineListEntity, fieldId: string) => listFieldMetaById.get(fieldId),
    [listFieldMetaById],
  );

  // The Table tab's visible rows — the current server page, not every filtered
  // row across all pages (see the Plan A spec's scope notes). Used for CSV
  // export, the custom list-view slot and the detail panel's prev/next
  // iterator. Read straight off the controller this page owns rather than
  // mirrored back out of PipelineListView: a skin that registers its own
  // `list-view` replaces that component entirely, and a round-trip through it
  // would leave every one of those consumers holding an empty list.
  const filteredEntities: PipelineListEntity[] = tableController.rows;

  const [selectedDetailEntityId, setSelectedDetailEntityId] = useState<string | null>(
    entityParam,
  );
  const [selectedDetailWorkflowId, setSelectedDetailWorkflowId] = useState<string | null>(
    enrollmentWorkflowParam,
  );
  const [addEntityOpen, setAddEntityOpen] = useState(false);

  // Keep the URL in sync so the detail view is directly linkable/refreshable,
  // not just closable — mirrors the `?entity=` deep-link read on mount above.
  const openDetailEntity = useCallback(
    (entityId: string, workflowId?: string) => {
      setSelectedDetailEntityId(entityId);
      setSelectedDetailWorkflowId(workflowId ?? null);
      setSearchParams((p) => {
        p.set('entity', entityId);
        if (workflowId) p.set('workflow', workflowId);
        else p.delete('workflow');
        return p;
      });
    },
    [setSearchParams],
  );

  // Carries the board's current query string (assignee/other filters) along
  // to the full-page detail route so its own back link can restore them —
  // otherwise navigating to a fresh `/pipeline/:id/entity/:entityId` URL
  // silently drops every `filter_*` param the board had applied.
  const handleEntityClick = (entityId: string, workflowId?: string) => {
    if (fullPageEnabled) {
      const qs = searchParams.toString();
      navigate(`/pipeline/${workflowId ?? id}/entity/${entityId}${qs ? `?${qs}` : ''}`);
      return;
    }
    openDetailEntity(entityId, workflowId);
  };

  // Sync deep-link `?entity=` param into state — or, when the org opens
  // details as a full page, forward the link there instead. Reuses the
  // board's own searchParams (minus `entity`) so `filter_*` keys ride along
  // the same way `handleEntityClick` above does for direct clicks. Neither
  // the kanban columns nor the table page reliably hold every entity anymore
  // (each loads its own bounded slice), so — unlike before — this no longer
  // gates on "is the entity already loaded somewhere"; `detailSummary` below
  // always resolves it with its own direct fetch.
  useEffect(() => {
    if (!entityParam) return;
    if (fullPageEnabled) {
      const params = new URLSearchParams(searchParams);
      params.delete('entity');
      const qs = params.toString();
      navigate(`/pipeline/${id}/entity/${entityParam}${qs ? `?${qs}` : ''}`, { replace: true });
      return;
    }
    setSelectedDetailEntityId(entityParam);
    setSelectedDetailWorkflowId(enrollmentWorkflowParam);
  }, [entityParam, enrollmentWorkflowParam, fullPageEnabled, id, navigate, searchParams]);

  const { data: detailSummary } = useQuery({
    queryKey: ['workflowEntitySummary', selectedDetailEntityId],
    queryFn: () => workflowEntities.get(selectedDetailEntityId ?? ''),
    enabled: !fullPageEnabled && Boolean(selectedDetailEntityId),
  });
  const {
    entity: detailEntity,
    loading: detailEntityLoading,
    error: detailEntityError,
    refetch: refetchDetailEntity,
  } = useFullWorkflowEntity(detailSummary ?? null);
  const {
    displayedEntity: displayedDetailEntity,
    displayLoading: detailLoading,
  } = resolveFullWorkflowEntityDisplay(
    detailSummary ?? null,
    detailEntity,
    detailEntityLoading,
    detailEntityError,
  );
  const detailEntityIndex = filteredEntities.findIndex(
    (entity) =>
      entity.entity_id === selectedDetailEntityId
      && (!selectedDetailWorkflowId || entity.workflow_id === selectedDetailWorkflowId),
  );
  const navigateDetailEntity = (offset: -1 | 1) => {
    const target = filteredEntities[detailEntityIndex + offset];
    if (target) openDetailEntity(target.entity_id, target.workflow_id);
  };

  const patchEntityData = useCallback(
    (entityId: string, data: Record<string, unknown>) => patchWorkflowEntityData(queryClient, entityId, data),
    [queryClient],
  );
  const refetchEntities = useCallback(async () => {
    invalidateWorkflowEntities(queryClient);
  }, [queryClient]);
  const updateEntity = useCallback(
    async (entityId: string, payload: Parameters<typeof workflowEntities.update>[1]) => {
      await workflowEntities.update(entityId, payload);
    },
    [],
  );

  if (loading) {
    return <div className="p-6 text-sm text-muted-foreground">Loading workflow…</div>;
  }

  if (fetchError || !workflow || !model) {
    return (
      <div className="p-6">
        <h1 className="mb-2 text-xl font-semibold text-foreground">Workflow not found</h1>
        <p className="mb-4 text-sm text-muted-foreground">
          {fetchError ?? (
            <>
              No workflow with id <code className="rounded bg-muted px-1 py-0.5">{id}</code>.
            </>
          )}
        </p>
        <Link to="/settings" className="text-sm text-cobalt hover:underline">
          Go to settings
        </Link>
      </div>
    );
  }

  if (!canView) {
    return (
      <div className="p-6">
        <AccessDenied entityType={workflow.entity_type} />
      </div>
    );
  }

  const isUnifiedToolbar = skin.board.toolbarLayout === 'unified';

  // Show/Hide control for terminal-state entities — only when the workflow has
  // terminal states, AND only for admin/superadmin: it writes an org-wide
  // preference (organization.settings), and the backend's branding endpoint
  // already restricts that write to admin/superadmin/owner roles. Everyone's
  // board still honors the saved preference; only these roles can change it.
  const canManageTerminalVisibility = isAdminRole(user?.role);
  const terminalStates = model.terminalStates;
  const terminalToggle = terminalStates.length > 0 && canManageTerminalVisibility ? (
    <PipelineTerminalToggle
      hidden={hideTerminal}
      label={terminalStates.length === 1 ? terminalStates[0].label : 'Terminal'}
      onToggle={setHideTerminal}
    />
  ) : null;

  // Rendered right after search (via BoardFilterBar's afterSearchSlot) — a
  // "who" filter reads as top-priority alongside search, not buried among
  // content-attribute filters like a department select.
  const assigneeAvatarFilterElement = (
    <AssigneeAvatarFilter
      options={assigneeFilter.options}
      hasUnassigned={assigneeFilter.hasUnassigned}
      selectedIds={assigneeFilter.selectedIds}
      onToggle={assigneeFilter.toggle}
      onClear={assigneeFilter.clear}
      currentUserId={user?.id}
    />
  );
  const customFilterElement = (
    <BoardCustomFilters
      available={customFilterOptions}
      selectedKeys={selectedCustomFilterKeys}
      onToggle={toggleCustomFilter}
    />
  );

  const viewTabsList = (
    // rounded-lg overrides the shared TabsList's default rounded-md so it
    // matches the rest of the filter row's controls (search, selects, Hide
    // Done, action buttons) — this page's own corner radius, not a change to
    // the shared primitive used elsewhere in the app.
    <TabsList className="self-start rounded-lg">
      {!hideKanban && (
        <TabsTrigger value="kanban">
          <LayoutGrid className="mr-1.5 h-4 w-4" />
          {skin.board.viewLabels?.kanban ?? 'Kanban'}
        </TabsTrigger>
      )}
      <TabsTrigger value="list">
        <ListChecks className="mr-1.5 h-4 w-4" />
        {skin.board.viewLabels?.list ?? 'List'}
      </TabsTrigger>
      {showCalendar && (
        <TabsTrigger value="calendar">
          <CalendarDays className="mr-1.5 h-4 w-4" />
          Calendar
        </TabsTrigger>
      )}
    </TabsList>
  );

  const ExportControlComponent = skin.board.exportStyle === 'csv' ? ExportCsvButton : ExportDropdown;
  const exportControl = hideExport ? undefined : (
    <ExportControlComponent
      entities={filteredEntities}
      schemaFields={model.schemaFields}
      fetchAllRows={tableController.fetchAllRows}
      workflowName={workflow.name}
    />
  );

  return (
    <div
      className={cn(
        'flex min-w-0 flex-col gap-3 overflow-hidden -mx-2 lg:-mx-6',
        // The platform's calc() height reserves the chrome above this page and
        // the layout's top padding. The page itself should reach the viewport
        // bottom, so do not reserve the layout's bottom padding here.
        skin.components?.topbar
          ? 'h-[calc(100svh-5rem)] lg:h-[calc(100svh-6rem)]'
          : skin.hideTopBar
            ? 'h-[calc(100svh-1rem)] lg:h-[calc(100svh-2rem)]'
            : navLayout === 'topbar'
              ? 'h-[calc(100svh-7.75rem)] lg:h-[calc(100svh-8.75rem)]'
              : 'h-[calc(100svh-5rem)] lg:h-[calc(100svh-6rem)]',
        skin.board.pagePaddingClassName,
      )}
    >
      <Tabs
        value={activeView}
        onValueChange={setActiveView}
        className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden"
      >
        <PipelinePageHeader
          workflow={workflow}
          onAddEntity={() => setAddEntityOpen(true)}
          canCreate={canCreate}
          bulkImportSlot={
            bulkImportEnabled && canCreate ? (
              <Button
                variant="outline"
                size="md"
                icon={<UploadCloud />}
                onClick={() =>
                  navigate(
                    `/bulk-import?entityType=${encodeURIComponent(workflow.entity_type)}&workflow=${encodeURIComponent(model.machineName)}`,
                  )
                }
              >
                Import and enroll
              </Button>
            ) : undefined
          }
          stackControls={!isUnifiedToolbar}
          viewToggle={
            isUnifiedToolbar ? (
              viewTabsList
            ) : (
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                {viewTabsList}
                {activeView !== 'calendar' && (
                  <BoardFilterBar
                    filters={filterConfig}
                    values={filterValues}
                    onChange={onFilterChange}
                    beforeSearchSlot={assigneeAvatarFilterElement}
                    afterSearchSlot={customFilterElement}
                    afterFiltersSlot={terminalToggle}
                  />
                )}
                {cardFieldsToggle}
              </div>
            )
          }
          exportSlot={isUnifiedToolbar ? undefined : exportControl}
        />

        {isUnifiedToolbar && (
          <div className="flex shrink-0 flex-wrap items-center gap-3">
            {activeView !== 'calendar' && (
              <BoardFilterBar
                filters={filterConfig}
                values={filterValues}
                onChange={onFilterChange}
                layout="toolbar"
                beforeSearchSlot={assigneeAvatarFilterElement}
                afterSearchSlot={customFilterElement}
                afterFiltersSlot={terminalToggle}
                trailingSlot={skin.board.showExportCsv !== false ? exportControl : undefined}
              />
            )}
            {cardFieldsToggle}
          </div>
        )}

        {!hideKanban && (
          <TabsContent value="kanban" className="mt-0 flex min-h-0 flex-1 overflow-hidden">
            <PipelineKanbanBoard
              key={`${model.machineName}:${JSON.stringify(columnFilters)}`}
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
              entityLabel={resolveEntityTypeLabel(workflow.entity_type)}
              cardFields={selectedCardFieldMeta}
            />
          </TabsContent>
        )}

        <TabsContent value="list" className="mt-0 min-h-0 flex-1 overflow-auto">
          <ComponentSlot
            slotName="list-view"
            component={skin.components?.['list-view']}
            slotProps={{
              model,
              entities: filteredEntities,
              onEntityClick: handleEntityClick,
            }}
            fallback={
              <PipelineListView
                key={model.machineName}
                model={model}
                controller={tableController}
                onEntityClick={handleEntityClick}
                showAssignee
                enableRowTransitions
                enableBulkActions
                canDelete={can('delete', workflow.entity_type)}
                bulkSelectionScopeKey={JSON.stringify(fieldFilters)}
                showSearch={false}
                resolveFieldMeta={resolveListFieldMeta}
                onTransitionExecuted={() => void refetchEntities()}
                onBulkMutationCommitted={() => void refetchEntities()}
              />
            }
          />
        </TabsContent>

        {showCalendar && (
          <TabsContent value="calendar" className="mt-0 min-h-0 flex-1 overflow-auto">
            <PipelineCalendarView
              model={model}
              entities={calendarListEntities}
              entitySchemas={entitySchemas}
              onEntityClick={handleEntityClick}
            />
          </TabsContent>
        )}
      </Tabs>

      <ComponentSlot
        slotName="entity-detail-view"
        component={skin.components?.['entity-detail-view']}
        slotProps={{
          entity: displayedDetailEntity ?? EMPTY_ENTITY,
          open: detailSummary != null,
          onClose: () => {
            setSelectedDetailEntityId(null);
            setSelectedDetailWorkflowId(null);
            setSearchParams((p) => { p.delete('entity'); p.delete('workflow'); p.delete('tab'); p.delete('comment'); p.delete('reply'); return p; });
          },
          onTransitionExecuted: () => {
            void refetchEntities();
            setSelectedDetailEntityId(null);
            setSelectedDetailWorkflowId(null);
            setSearchParams((p) => { p.delete('entity'); p.delete('workflow'); p.delete('tab'); p.delete('comment'); p.delete('reply'); return p; });
          },
          onDeleted: () => {
            void refetchEntities();
            setSelectedDetailEntityId(null);
            setSelectedDetailWorkflowId(null);
            setSearchParams((p) => { p.delete('entity'); p.delete('workflow'); p.delete('tab'); p.delete('comment'); p.delete('reply'); return p; });
          },
        }}
        fallback={
          <EntityDetailSlideOver
            entity={displayedDetailEntity}
            open={detailSummary != null}
            loading={detailLoading}
            onClose={() => {
              setSelectedDetailEntityId(null);
              setSelectedDetailWorkflowId(null);
              setSearchParams((p) => { p.delete('entity'); p.delete('workflow'); p.delete('tab'); p.delete('comment'); p.delete('reply'); return p; });
            }}
            // Same strict rule as the full-page detail view: only the fields
            // this record's current state collects.
            schemas={schemasForState(displayedDetailEntity?.current_state)}
            schemasAuthoritative
            onSaveEntity={updateEntity}
            onFileUploaded={() => { void refetchEntities(); refetchDetailEntity(); }}
            initialTab={tabParam === 'comments' || tabParam === 'activity' ? tabParam : undefined}
            scrollToCommentId={commentParam}
            scrollToReplyId={replyParam}
            workflowId={id}
            onTransitionExecuted={() => {
              void refetchEntities();
              refetchDetailEntity();
            }}
            onEntityDataSaved={(newData) => {
              if (!selectedDetailEntityId) return;
              patchEntityData(selectedDetailEntityId, newData);
              void refetchEntities();
              refetchDetailEntity();
            }}
            onDeleted={() => {
              void refetchEntities();
              setSelectedDetailEntityId(null);
              setSelectedDetailWorkflowId(null);
              setSearchParams((p) => { p.delete('entity'); p.delete('workflow'); p.delete('tab'); p.delete('comment'); p.delete('reply'); return p; });
            }}
            iterator={
              detailEntityIndex >= 0
                ? {
                    current: detailEntityIndex + 1,
                    total: filteredEntities.length,
                    onPrevious: () => navigateDetailEntity(-1),
                    onNext: () => navigateDetailEntity(1),
                  }
                : undefined
            }
          />
        }
      />

      <AddEntityDialog
        open={addEntityOpen}
        onClose={() => setAddEntityOpen(false)}
        workflow={workflow}
        // A new record starts at the initial state, so it can only fill the
        // fields that state's Methods collect.
        schemas={creationSchemas}
        schemasLoading={entitySchemasLoading}
        schemasError={entitySchemasError}
        onCreated={() => void refetchEntities()}
      />
    </div>
  );
}
