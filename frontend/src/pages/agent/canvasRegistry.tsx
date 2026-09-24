import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import type { ComponentType } from 'react';
import { WidgetCard } from '@/pages/dashboard/components/WidgetCard';
import PipelineBoardWidget from '@/pages/Pipeline/PipelineBoardWidget';
import PipelineCalendarView from '@/pages/Pipeline/components/PipelineCalendarView';
import EntityTable from '@/pages/records/detail/components/EntityTable';
import { usePipelineBoardData, toListEntity } from '@/pages/Pipeline/hooks/usePipelineBoardData';
import { useWorkflowEntities } from '@/shared/hooks';
import { useEntityStore, schemaForEntityType } from '@/core/stores/entityStore';
import { mapEnrollmentSummary } from '@/core/services/api/workflowEntities';
import type { DashboardWidgetDef, DashboardWidgetData } from '@/core/types';
import type { WorkflowEntityState } from '@/core/services/api';

/**
 * Registry of the app's REAL components the agent can render "on the fly" by name.
 * The backend `render_ui_component` tool emits `{ __render__: { component: <key>, props } }`
 * and the canvas looks the key up here. Every entry renders an actual app
 * component (never a look-alike): `WidgetCard` (the exact dashboard dispatcher),
 * the self-fetching `PipelineBoardWidget`, `PipelineCalendarView`, and `EntityTable`.
 * The model only chooses WHAT to show — the components fetch/compute the data.
 */

const noop = () => {};

/** Opens a real record page in a new tab — not in-page navigate(), which would
 *  unmount AgentModePage and drop the whole conversation/canvas. */
function openInNewTab(path: string) {
  window.open(path, '_blank', 'noopener,noreferrer');
}

// --- Dashboard ---------------------------------------------------------------

function DashboardWidgetCanvasView({ def, data }: { def: DashboardWidgetDef; data?: DashboardWidgetData }) {
  return (
    <WidgetCard
      widget={def}
      data={data}
      editMode={false}
      onEdit={noop}
      onRemove={noop}
      onNavigate={openInNewTab}
    />
  );
}

function DashboardCanvasView({ widgets }: { widgets: Array<{ def: DashboardWidgetDef; data?: DashboardWidgetData }> }) {
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      {widgets.map((w) => (
        <div key={w.def.id} className="min-h-[12rem]">
          <WidgetCard
            widget={w.def}
            data={w.data}
            editMode={false}
            onEdit={noop}
            onRemove={noop}
            onNavigate={openInNewTab}
          />
        </div>
      ))}
    </div>
  );
}

// --- Workflows ---------------------------------------------------------------

function PipelineBoardCanvasView({ workflowId, view }: { workflowId: string; view?: 'kanban' | 'list' }) {
  // The assignee filter (useAssigneeFilter) writes its selection straight
  // into this page's own URL via useSearchParams, so the live agent-mode URL
  // already carries e.g. `?filter_assignee_<machine>=...` while the board is
  // filtered. Capturing that full path+search here (instead of a bare
  // "/agent") means clicking into an entity and back restores that filter
  // too, not just the conversation.
  const location = useLocation();
  return (
    <div className="h-full min-h-0 overflow-hidden rounded-xl border border-border bg-card p-3">
      <PipelineBoardWidget
        workflowId={workflowId}
        view={view === 'list' ? 'list' : 'kanban'}
        showTransitions
        showToolbar
        returnTo={`${location.pathname}${location.search}`}
      />
    </div>
  );
}

function PipelineCalendarCanvasView({ workflowId }: { workflowId: string }) {
  const { workflow, loading, error, model, summaryFields, canView } = usePipelineBoardData(workflowId);
  const { entities } = useWorkflowEntities(model?.machineName, undefined, {
    stateNames: model?.states.map((state) => state.name),
    summaryFields,
  });
  if (loading) return <div className="text-sm text-muted-foreground">Loading pipeline…</div>;
  if (error || !workflow || !model) {
    return <div className="text-sm text-destructive">{error ?? 'Pipeline not found.'}</div>;
  }
  if (!canView) {
    return <div className="text-sm text-muted-foreground">You don't have permission to view this pipeline.</div>;
  }
  return (
    <div className="h-full min-h-0 overflow-auto rounded-xl border border-border bg-card p-3">
      <PipelineCalendarView
        model={model}
        entities={entities.map(toListEntity)}
        onEntityClick={(entityId) => openInNewTab(`/pipeline/${workflowId}/entity/${entityId}`)}
      />
    </div>
  );
}

// --- Records table -----------------------------------------------------------

function EntityTableCanvasView({
  entities: rawEntities,
  workflowId,
  entityType,
}: {
  // The backend serialises WorkflowEnrollmentSummary objects (summary_fields,
  // entity_created_at) but EntityTable expects WorkflowEntityState (data,
  // created_at). Accept either shape and normalise via mapEnrollmentSummary.
  entities: (WorkflowEntityState | Record<string, unknown>)[];
  workflowId?: string;
  entityType?: string;
}) {
  const entities = rawEntities.map((e) =>
    'summary_fields' in e
      ? mapEnrollmentSummary(e as Parameters<typeof mapEnrollmentSummary>[0])
      : (e as WorkflowEntityState),
  );
  const schemas = useEntityStore((s) => s.schemas);
  const fetchSchemas = useEntityStore((s) => s.fetchSchemas);

  // Load form schemas so preview fields render exactly like the records page
  // (falls back to a field count only if schemas are unavailable).
  useEffect(() => {
    if (schemas.length === 0) void fetchSchemas();
  }, [schemas.length, fetchSchemas]);

  return (
    <EntityTable
      entities={entities}
      columnScope={entityType ?? 'agent-canvas'}
      schemaForEntity={(entity) => schemaForEntityType(schemas, entity.entity_type)}
      deletingEntityId={null}
      onEdit={(entity) => workflowId && openInNewTab(`/pipeline/${workflowId}/entity/${entity.entity_id}`)}
      onDelete={noop}
      canEdit={false}
      canDelete={false}
      canView={Boolean(workflowId)}
    />
  );
}

// --- Stat tile (back-compat) -------------------------------------------------

interface StatTileProps {
  value: number;
  prevValue?: number;
  subtitle?: string;
}

function StatTileCanvasView({ value, prevValue, subtitle }: StatTileProps) {
  // stat_tile returns a scalar-shaped payload; render it through the real
  // dashboard stat widget for visual parity.
  const def: DashboardWidgetDef = {
    id: 'agent-stat-tile',
    type: 'stat',
    title: subtitle ?? 'Metric',
    layout: { x: 0, y: 0, w: 12, h: 4 },
    subtitle,
  };
  const data: DashboardWidgetData = { kind: 'scalar', value, prevValue };
  return (
    <WidgetCard widget={def} data={data} editMode={false} onEdit={noop} onRemove={noop} onNavigate={openInNewTab} />
  );
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const canvasRegistry: Record<string, ComponentType<any>> = {
  dashboard: DashboardCanvasView,
  dashboard_widget: DashboardWidgetCanvasView,
  pipeline_board: PipelineBoardCanvasView,
  pipeline_list: (props: { workflowId: string }) => <PipelineBoardCanvasView workflowId={props.workflowId} view="list" />,
  pipeline_calendar: PipelineCalendarCanvasView,
  entity_table: EntityTableCanvasView,
  stat_tile: StatTileCanvasView,
};
